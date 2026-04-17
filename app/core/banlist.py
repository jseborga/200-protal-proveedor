"""Sistema de banlist: honeypot + deteccion de burst + middleware de bloqueo.

Flujo:
1. Middleware ASGI `BanCheckMiddleware` lee la IP real en cada request.
2. Si esta en la cache (sincronizada con la tabla mkt_banned_ip), devuelve 403.
3. Para paths sospechosos (honeypot) banea permanentemente y responde 404.
4. Para paths publicos (/api/v1/*/public*) cuenta hits en ventana rodante;
   si supera el umbral banea por 1 hora.

Se implementa como ASGI puro (no BaseHTTPMiddleware) para evitar
incompatibilidades de Starlette con requests que tienen body (POST /login).

La cache es un set en memoria; se recarga desde BD al arrancar y cuando se
agrega un nuevo baneo. Para multi-worker real usar RATELIMIT_STORAGE_URI=redis://
y un store compartido; aqui cada worker mantiene su propia vista (aceptable
para efecto disuasorio).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import async_session
from app.models.banned_ip import BannedIP


# ── Configuracion ──────────────────────────────────────────────
# Kill switch: DISABLE_BAN_CHECK=1 desactiva todo el middleware.
DISABLE_BAN_CHECK = os.getenv("DISABLE_BAN_CHECK", "0") == "1"

BURST_WINDOW_SEC = int(os.getenv("BURST_WINDOW_SEC", "10"))
BURST_THRESHOLD = int(os.getenv("BURST_THRESHOLD", "300"))  # hits en la ventana
BURST_BAN_MINUTES = int(os.getenv("BURST_BAN_MINUTES", "60"))

# Paths trampa. Anonimo que los toca se banea permanentemente.
# Solo paths exactos; evitamos matchers genericos (*.php, /wp-*) porque
# navegadores y apps legitimas pueden tocarlos accidentalmente.
HONEYPOT_PATHS = {
    "/api/v1/prices/internal-dump",
    "/api/v1/suppliers/export-all",
    "/api/v1/admin/full-export",
    "/admin.php",
    "/wp-admin/",
    "/wp-login.php",
    "/.env",
    "/.git/config",
    "/phpmyadmin/",
    "/phpMyAdmin/",
    "/xmlrpc.php",
}

# Prefijos cuya acumulacion cuenta contra el burst counter
TRACKED_PREFIXES = (
    "/api/v1/prices/public",
    "/api/v1/suppliers/public",
    "/api/v1/prices/public/search",
)


def _is_private_ip(ip: str) -> bool:
    """IPs privadas / loopback no se banean: suelen ser el reverse proxy."""
    if not ip or ip == "unknown":
        return True
    if ip.startswith(("127.", "10.", "192.168.", "169.254.", "::1", "fc", "fd")):
        return True
    # 172.16.0.0/12
    if ip.startswith("172."):
        try:
            second = int(ip.split(".")[1])
            if 16 <= second <= 31:
                return True
        except (ValueError, IndexError):
            pass
    return False


# ── Cache en memoria ───────────────────────────────────────────
_banned_cache: dict[str, float] = {}  # ip -> expires_at_epoch (inf para permanente)
_burst_hits: dict[str, deque] = defaultdict(deque)
_INF = float("inf")


async def reload_ban_cache() -> None:
    """Carga todos los baneos vigentes desde BD."""
    global _banned_cache
    now = datetime.now(timezone.utc)
    new_cache: dict[str, float] = {}
    async with async_session() as db:
        result = await db.execute(select(BannedIP))
        for b in result.scalars().all():
            if b.expires_at is None:
                new_cache[b.ip] = _INF
            elif b.expires_at > now:
                new_cache[b.ip] = b.expires_at.timestamp()
    _banned_cache = new_cache


def _is_banned(ip: str) -> bool:
    exp = _banned_cache.get(ip)
    if exp is None:
        return False
    if exp == _INF:
        return True
    if exp > time.time():
        return True
    _banned_cache.pop(ip, None)
    return False


def _ban_cache_add(ip: str, minutes: int | None) -> None:
    """Actualiza la cache en memoria de forma sincrona."""
    if minutes is None:
        _banned_cache[ip] = _INF
    else:
        _banned_cache[ip] = time.time() + minutes * 60


async def ban_ip(
    ip: str,
    reason: str,
    path: str | None = None,
    user_agent: str | None = None,
    minutes: int | None = None,
) -> None:
    """Registra un baneo en BD y lo agrega a la cache. minutes=None = permanente.

    La cache se actualiza sincronamente al arrancar la corutina; la escritura
    en BD se ejecuta al await y puede fallar silenciosamente.
    """
    _ban_cache_add(ip, minutes)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=minutes) if minutes else None
    try:
        async with async_session() as db:
            stmt = pg_insert(BannedIP).values(
                ip=ip,
                reason=reason,
                path=(path or "")[:500],
                user_agent=(user_agent or "")[:500],
                hits=1,
                expires_at=expires_at,
            ).on_conflict_do_update(
                index_elements=["ip"],
                set_={
                    "reason": reason,
                    "path": (path or "")[:500],
                    "user_agent": (user_agent or "")[:500],
                    "hits": BannedIP.__table__.c.hits + 1,
                    "expires_at": expires_at,
                    "updated_at": now,
                },
            )
            await db.execute(stmt)
            await db.commit()
    except Exception:
        pass


def _record_hit(ip: str) -> bool:
    dq = _burst_hits[ip]
    now = time.time()
    cutoff = now - BURST_WINDOW_SEC
    while dq and dq[0] < cutoff:
        dq.popleft()
    dq.append(now)
    return len(dq) >= BURST_THRESHOLD


# ── Helpers ASGI ───────────────────────────────────────────────
def _headers_dict(scope) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}


def _client_ip_from_scope(scope) -> str:
    headers = _headers_dict(scope)
    cf = headers.get("cf-connecting-ip")
    if cf:
        return cf
    fwd = headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    real = headers.get("x-real-ip")
    if real:
        return real
    client = scope.get("client")
    return client[0] if client else "unknown"


async def _send_json(send, status_code: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status_code,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("latin-1")),
        ],
    })
    await send({"type": "http.response.body", "body": body, "more_body": False})


# ── Middleware ASGI puro ───────────────────────────────────────
class BanCheckMiddleware:
    """Bloquea IPs baneadas, dispara honeypot y detecta burst.

    Implementacion ASGI pura: no usa BaseHTTPMiddleware para evitar
    conflictos con requests que llevan body (POST, PUT) cuando se combinan
    varios BaseHTTPMiddleware + SlowAPIMiddleware.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or DISABLE_BAN_CHECK:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        ip = _client_ip_from_scope(scope)

        # Nunca banear IPs privadas / proxies internos.
        if _is_private_ip(ip):
            await self.app(scope, receive, send)
            return

        if _is_banned(ip):
            await _send_json(send, 403, {"ok": False, "error": "access_denied"})
            return

        # Honeypot: paths trampa exactos
        if path in HONEYPOT_PATHS:
            ua = _headers_dict(scope).get("user-agent", "")
            _ban_cache_add(ip, None)
            asyncio.create_task(
                ban_ip(ip, "honeypot", path=path, user_agent=ua, minutes=None)
            )
            await _send_json(send, 404, {"ok": False, "error": "not_found"})
            return

        # Deteccion de burst solo en endpoints publicos trackeados sin auth
        if path.startswith(TRACKED_PREFIXES):
            headers = _headers_dict(scope)
            if not headers.get("authorization"):
                if _record_hit(ip):
                    ua = headers.get("user-agent", "")
                    _ban_cache_add(ip, BURST_BAN_MINUTES)
                    asyncio.create_task(
                        ban_ip(
                            ip,
                            reason="burst",
                            path=path,
                            user_agent=ua,
                            minutes=BURST_BAN_MINUTES,
                        )
                    )
                    await _send_json(send, 429, {"ok": False, "error": "rate_abuse"})
                    return

        await self.app(scope, receive, send)
