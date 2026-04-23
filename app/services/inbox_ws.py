"""Broadcaster in-memory para WebSocket live updates del Inbox (Fase 5.11).

Arquitectura:
- Un dict `_subs: {user_id: set[WebSocket]}` mantiene los subscribers.
- Un cache `_user_roles: {user_id: role}` evita tocar DB en el hot path.
- `publish_event` es la API publica que usan los callers (routes/services).

Limitaciones conocidas (Fase 5.11):
- Soporta solo WORKERS=1. Para multi-worker habra que mover a Redis pub/sub
  detras de la misma API `publish_event` sin tocar callers.
- Eventos efimeros (no persistidos). Los clientes resincronizan via polling
  degradado (60s cuando WS open, 10s en fallback).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Iterable

from starlette.websockets import WebSocket, WebSocketState

logger = logging.getLogger(__name__)

# Roles con acceso al inbox/conversation hub
STAFF_ROLES: frozenset[str] = frozenset(
    {"field_agent", "manager", "admin", "superadmin"}
)

# Estado interno (solo se muta bajo _lock)
_subs: dict[int, set[WebSocket]] = {}
_user_roles: dict[int, str] = {}
_lock = asyncio.Lock()


async def register_subscriber(
    user_id: int,
    ws: WebSocket,
    *,
    role: str,
) -> None:
    """Registra un WebSocket como subscriber del user_id dado."""
    async with _lock:
        if user_id not in _subs:
            _subs[user_id] = set()
        _subs[user_id].add(ws)
        _user_roles[user_id] = role


async def unregister_subscriber(user_id: int, ws: WebSocket) -> None:
    """Desregistra un WebSocket. Limpia la entry del user si queda vacia."""
    async with _lock:
        if user_id in _subs:
            _subs[user_id].discard(ws)
            if not _subs[user_id]:
                del _subs[user_id]
                _user_roles.pop(user_id, None)


async def broadcast_to_user(user_id: int, payload: dict) -> int:
    """Envia payload a todos los sockets del user. Limpia sockets muertos.

    Devuelve la cantidad de sockets a los que se envio con exito.
    """
    # Snapshot de sockets bajo lock (copia, para iterar fuera del lock)
    async with _lock:
        sockets = list(_subs.get(user_id, set()))
    if not sockets:
        return 0

    sent = 0
    dead: list[WebSocket] = []
    for ws in sockets:
        try:
            # Best-effort: evita enviar a sockets ya cerrados
            if (
                ws.client_state == WebSocketState.DISCONNECTED
                or ws.application_state == WebSocketState.DISCONNECTED
            ):
                dead.append(ws)
                continue
            await ws.send_json(payload)
            sent += 1
        except Exception:  # noqa: BLE001
            dead.append(ws)

    if dead:
        async with _lock:
            entry = _subs.get(user_id)
            if entry is not None:
                for ws in dead:
                    entry.discard(ws)
                if not entry:
                    del _subs[user_id]
                    _user_roles.pop(user_id, None)
    return sent


def _build_payload(event_type: str, data: dict) -> dict:
    """Construye el payload estandar."""
    return {
        "type": "inbox_event",
        "event": event_type,
        "data": data,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


async def publish_event(
    event_type: str,
    data: dict,
    *,
    target_roles: Iterable[str] | None = None,
    exclude_user_id: int | None = None,
) -> int:
    """Publica un evento a todos los subscribers staff.

    - `target_roles`: si se indica, solo users con role en esa coleccion
      reciben. Default: `STAFF_ROLES`.
    - `exclude_user_id`: suprime el envio a ese user (evita eco al emisor).

    Devuelve la cantidad total de sockets alcanzados.
    NUNCA lanza: atrapa cualquier error internamente para no romper callers.
    """
    try:
        payload = _build_payload(event_type, data)
        roles = frozenset(target_roles) if target_roles else STAFF_ROLES

        # Snapshot de user_ids a notificar bajo lock
        async with _lock:
            candidates = [
                uid
                for uid, role in _user_roles.items()
                if role in roles and uid != exclude_user_id
            ]

        total = 0
        for uid in candidates:
            total += await broadcast_to_user(uid, payload)
        return total
    except Exception:  # noqa: BLE001
        logger.exception("inbox_ws.publish_event fallo (event=%s)", event_type)
        return 0


# ── Wrappers semanticos (Fase 5.11) ─────────────────────────────
#
# 4 familias consolidadas:
#   1. message.created        (kind: inbound|outbound|note|system)
#   2. session.operator_changed (reason: claim|release|assign|auto_assign|auto_handoff)
#   3. session.state_changed   (prev_state, state)
#   4. session.marked_read     (mantiene shape previo)
#
# NUNCA lanzan. Internamente delegan en publish_event que ya atrapa todo.


MESSAGE_KINDS = frozenset({"inbound", "outbound", "note", "system"})
OPERATOR_CHANGE_REASONS = frozenset(
    {"claim", "release", "assign", "auto_assign", "auto_handoff"}
)


async def publish_message_created(
    session_id: int,
    message_id: int | None,
    kind: str,
    *,
    preview: str | None = None,
    exclude_user_id: int | None = None,
) -> int:
    """Publica message.created. Emite solo si kind es valido."""
    if kind not in MESSAGE_KINDS:
        return 0
    data: dict = {"session_id": int(session_id), "kind": kind}
    if message_id is not None:
        data["message_id"] = int(message_id)
    if preview is not None:
        # Cap preview a 140 chars para no saturar el canal.
        data["preview"] = preview[:140]
    return await publish_event(
        "message.created", data, exclude_user_id=exclude_user_id
    )


async def publish_session_operator_changed(
    session_id: int,
    prev_operator_id: int | None,
    operator_id: int | None,
    reason: str,
    *,
    by_user_id: int | None = None,
    strategy: str | None = None,
    exclude_user_id: int | None = None,
) -> int:
    """Publica session.operator_changed. Emite solo si reason es valido."""
    if reason not in OPERATOR_CHANGE_REASONS:
        return 0
    data: dict = {
        "session_id": int(session_id),
        "prev_operator_id": prev_operator_id,
        "operator_id": operator_id,
        "reason": reason,
    }
    if by_user_id is not None:
        data["by_user_id"] = int(by_user_id)
    if strategy is not None:
        data["strategy"] = strategy
    return await publish_event(
        "session.operator_changed", data, exclude_user_id=exclude_user_id
    )


async def publish_session_state_changed(
    session_id: int,
    prev_state: str | None,
    state: str,
    *,
    pedido_id: int | None = None,
    mode: str | None = None,
    exclude_user_id: int | None = None,
) -> int:
    """Publica session.state_changed."""
    if prev_state == state:
        return 0
    data: dict = {
        "session_id": int(session_id),
        "prev_state": prev_state,
        "state": state,
    }
    if pedido_id is not None:
        data["pedido_id"] = int(pedido_id)
    if mode is not None:
        data["mode"] = mode
    return await publish_event(
        "session.state_changed", data, exclude_user_id=exclude_user_id
    )


def connected_users_count() -> int:
    """Cantidad de users con al menos un socket conectado."""
    return len(_subs)


def total_sockets_count() -> int:
    """Cantidad total de sockets conectados."""
    return sum(len(s) for s in _subs.values())


# Util para tests: limpia estado global
async def _reset_state() -> None:  # pragma: no cover - test helper
    async with _lock:
        _subs.clear()
        _user_roles.clear()
