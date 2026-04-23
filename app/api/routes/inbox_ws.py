"""Endpoint WebSocket para live updates del Inbox (Fase 5.11).

El cliente debe autenticarse con un JWT enviado como query param
(`?token=...`) ya que WebSocket no soporta headers custom desde el browser.

Flujo:
1. Valida el JWT con `decode_token`.
2. Carga el `User`; rechaza si no esta activo o no es staff.
3. Acepta el socket, lo registra en el broadcaster in-memory.
4. Corre dos tareas: heartbeat (server->cliente cada 30s) y receive loop
   (drenaje de mensajes del cliente: client_ping, pong, noop).
5. En desconexion, desregistra limpiamente.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.services.inbox_ws import (
    STAFF_ROLES,
    register_subscriber,
    unregister_subscriber,
)

logger = logging.getLogger(__name__)
router = APIRouter()

HEARTBEAT_INTERVAL_S = 30.0


async def _heartbeat_loop(websocket: WebSocket) -> None:
    """Envia pings periodicos al cliente. Termina si el socket cae."""
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            await websocket.send_json({"type": "ping"})
    except (WebSocketDisconnect, asyncio.CancelledError):
        raise
    except Exception:  # noqa: BLE001
        # Error al enviar ping -> cerramos para forzar reconnect
        return


async def _receive_loop(websocket: WebSocket) -> None:
    """Drena mensajes del cliente (pong, client_ping, etc). No los procesa."""
    try:
        while True:
            # Si el cliente cierra, receive_text lanza WebSocketDisconnect.
            await websocket.receive_text()
    except (WebSocketDisconnect, asyncio.CancelledError):
        raise
    except Exception:  # noqa: BLE001
        return


@router.websocket("/ws")
async def inbox_ws_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
    db: AsyncSession = Depends(get_db),
):
    """Endpoint WebSocket del inbox.

    Cierre codes:
    - 1008 (policy violation): token invalido, user inactivo o no staff.
    - 1000 (normal): desconexion del cliente.
    """
    # 1. Validar JWT
    try:
        payload = decode_token(token)
    except Exception:  # noqa: BLE001
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    sub = payload.get("sub")
    if not sub:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Cargar user y validar staff + activo
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user = await db.get(User, user_id)
    if user is None or not user.is_active or user.role not in STAFF_ROLES:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 3. Aceptar + registrar
    await websocket.accept()
    await register_subscriber(user.id, websocket, role=user.role)
    logger.info("inbox_ws connected user=%s role=%s", user.id, user.role)

    # Saludo opcional con metadata (util para debugging en cliente)
    try:
        await websocket.send_json(
            {
                "type": "hello",
                "data": {"user_id": user.id, "role": user.role},
            }
        )
    except Exception:  # noqa: BLE001
        await unregister_subscriber(user.id, websocket)
        return

    # 4. Correr heartbeat + receive loops en paralelo
    heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket))
    receive_task = asyncio.create_task(_receive_loop(websocket))
    try:
        done, pending = await asyncio.wait(
            {heartbeat_task, receive_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
    except Exception:  # noqa: BLE001
        logger.exception("inbox_ws loop error user=%s", user.id)
    finally:
        # 5. Cleanup
        await unregister_subscriber(user.id, websocket)
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
        logger.info("inbox_ws disconnected user=%s", user.id)
