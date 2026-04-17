"""Sistema de banlist: honeypot + deteccion de burst + middleware de bloqueo.

Flujo:
1. Middleware `BanCheckMiddleware` lee la IP real en cada request.
2. Si esta en la cache (sincronizada con la tabla mkt_banned_ip), devuelve 403.
3. Para paths sospechosos (honeypot) banea permanentemente y responde 403.
4. Para paths publicos (/api/v1/*/public*) cuenta hits en ventana rodante;
   si supera el umbral banea por 1 hora.

La cache es un set en memoria; se recarga desde BD al arrancar y cuando se
agrega un nuevo baneo. Para multi-worker real usar RATELIMIT_STORAGE_URI=redis://
y un store compartido; aqui cada worker mantiene su propia vista (aceptable
para efecto disuasorio).
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.database import async_session
from app.core.rate_limit import _client_key
from app.models.banned_ip import BannedIP


# ── Configuracion ──────────────────────────────────────────────
BURST_WINDOW_SEC = int(os.getenv("BURST_WINDOW_SEC", "10"))
BURST_THRESHOLD = int(os.getenv("BURST_THRESHOLD", "100"))  # hits en la ventana
BURST_BAN_MINUTES = int(os.getenv("BURST_BAN_MINUTES", "60"))

# Paths trampa. Anonimo que los toca se banea permanentemente.
# Se publican en robots.txt como Disallow para que bots que ignoran las
# reglas caigan, y a la vez se excluyen legalmente via robots.txt.
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
}

# Prefijos cuya acumulacion cuenta contra el burst counter
TRACKED_PREFIXES = (
    "/api/v1/prices/public",
    "/api/v1/suppliers/public",
    "/api/v1/prices/public/search",
)


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
    # Expirado — limpiar
    _banned_cache.pop(ip, None)
    return False


async def ban_ip(
    ip: str,
    reason: str,
    path: str | None = None,
    user_agent: str | None = None,
    minutes: int | None = None,
) -> None:
    """Registra un baneo en BD y lo agrega a la cache en memoria.

    minutes=None = permanente.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=minutes) if minutes else None
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
    _banned_cache[ip] = _INF if expires_at is None else expires_at.timestamp()


def _record_hit(ip: str) -> bool:
    """Registra un hit y retorna True si supera el umbral de burst."""
    dq = _burst_hits[ip]
    now = time.time()
    cutoff = now - BURST_WINDOW_SEC
    while dq and dq[0] < cutoff:
        dq.popleft()
    dq.append(now)
    return len(dq) >= BURST_THRESHOLD


# ── Middleware ─────────────────────────────────────────────────
class BanCheckMiddleware(BaseHTTPMiddleware):
    """Bloquea IPs baneadas, dispara honeypot y detecta burst."""

    async def dispatch(self, request: Request, call_next):
        ip = _client_key(request)
        path = request.url.path

        if _is_banned(ip):
            return JSONResponse(
                {"ok": False, "error": "access_denied"},
                status_code=403,
            )

        # Honeypot: paths trampa banean permanentemente
        if path in HONEYPOT_PATHS or path.startswith("/wp-") or path.endswith(".php"):
            ua = request.headers.get("user-agent", "")
            try:
                await ban_ip(ip, "honeypot", path=path, user_agent=ua, minutes=None)
            except Exception:
                pass
            return JSONResponse(
                {"ok": False, "error": "not_found"},
                status_code=404,
            )

        # Deteccion de burst solo en endpoints trackeados y sin auth
        if path.startswith(TRACKED_PREFIXES) and not request.headers.get("authorization"):
            if _record_hit(ip):
                ua = request.headers.get("user-agent", "")
                try:
                    await ban_ip(
                        ip,
                        reason="burst",
                        path=path,
                        user_agent=ua,
                        minutes=BURST_BAN_MINUTES,
                    )
                except Exception:
                    pass
                return JSONResponse(
                    {"ok": False, "error": "rate_abuse"},
                    status_code=429,
                )

        return await call_next(request)
