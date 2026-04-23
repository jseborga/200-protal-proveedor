"""Tests de integracion Fase 5.11: endpoint WebSocket /api/v1/inbox/ws.

Usa starlette.testclient.TestClient.websocket_connect (sincronico).
Se ejecuta dentro de asyncio.to_thread para no bloquear el event loop.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.routes.inbox_ws import router as inbox_ws_router
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user import User
from app.services import inbox_ws


@pytest_asyncio.fixture(autouse=True)
async def _reset_ws_state():
    await inbox_ws._reset_state()
    yield
    await inbox_ws._reset_state()


@pytest_asyncio.fixture
async def staff_user(db) -> User:
    u = User(
        email="staff@test.com",
        hashed_password="x",
        full_name="Staff",
        role="field_agent",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def manager_user(db) -> User:
    u = User(
        email="mgr@test.com",
        hashed_password="x",
        full_name="Mgr",
        role="manager",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def buyer_user(db) -> User:
    u = User(
        email="buyer@test.com",
        hashed_password="x",
        full_name="Buyer",
        role="buyer",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def inactive_staff(db) -> User:
    u = User(
        email="dis@test.com",
        hashed_password="x",
        full_name="Dis",
        role="manager",
        is_active=False,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def app(db):
    app = FastAPI()
    app.include_router(inbox_ws_router, prefix="/api/v1/inbox")

    async def _get_db_override():
        yield db

    app.dependency_overrides[get_db] = _get_db_override
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def _token_for(user: User) -> str:
    return create_access_token({"sub": str(user.id)})


def _connect_sync(client: TestClient, url: str):
    """Ayudante sincronico: devuelve el context manager de TestClient.websocket_connect."""
    return client.websocket_connect(url)


class TestAuthentication:
    async def test_rejects_missing_token(self, client):
        def _try():
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect("/api/v1/inbox/ws"):
                    pass
            return exc.value

        exc = await asyncio.to_thread(_try)
        # Sin token, FastAPI devuelve 403 (Query requerido) antes de accept.
        # Es aceptable cualquier cierre temprano.
        assert exc is not None

    async def test_rejects_invalid_token(self, client):
        def _try():
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect(
                    "/api/v1/inbox/ws?token=not-a-jwt"
                ):
                    pass
            return exc.value

        exc = await asyncio.to_thread(_try)
        assert exc.code == 1008

    async def test_rejects_expired_token(self, client, staff_user):
        expired = create_access_token(
            {"sub": str(staff_user.id)},
            expires_delta=timedelta(seconds=-60),
        )

        def _try():
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect(
                    f"/api/v1/inbox/ws?token={expired}"
                ):
                    pass
            return exc.value

        exc = await asyncio.to_thread(_try)
        assert exc.code == 1008

    async def test_rejects_non_staff_role(self, client, buyer_user):
        token = _token_for(buyer_user)

        def _try():
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect(
                    f"/api/v1/inbox/ws?token={token}"
                ):
                    pass
            return exc.value

        exc = await asyncio.to_thread(_try)
        assert exc.code == 1008

    async def test_rejects_inactive_user(self, client, inactive_staff):
        token = _token_for(inactive_staff)

        def _try():
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect(
                    f"/api/v1/inbox/ws?token={token}"
                ):
                    pass
            return exc.value

        exc = await asyncio.to_thread(_try)
        assert exc.code == 1008


class TestConnectAndEvents:
    async def test_accepts_valid_staff_token(self, client, staff_user):
        token = _token_for(staff_user)

        def _try():
            with client.websocket_connect(
                f"/api/v1/inbox/ws?token={token}"
            ) as ws:
                greeting = ws.receive_json()
                return greeting

        greeting = await asyncio.to_thread(_try)
        assert greeting["type"] == "hello"
        assert greeting["data"]["user_id"] == staff_user.id
        assert greeting["data"]["role"] == "field_agent"

    async def test_receives_published_event(self, client, staff_user):
        token = _token_for(staff_user)
        staff_uid = staff_user.id
        loop = asyncio.get_event_loop()

        def _try():
            with client.websocket_connect(
                f"/api/v1/inbox/ws?token={token}"
            ) as ws:
                # Drop greeting
                ws.receive_json()
                # Publicar desde el main loop (thread-safe)
                fut = asyncio.run_coroutine_threadsafe(
                    inbox_ws.publish_event(
                        "session.claimed",
                        {"session_id": 42, "operator_id": 99},
                    ),
                    loop,
                )
                sent = fut.result(timeout=2.0)
                assert sent >= 1
                event = ws.receive_json()
                return event

        event = await asyncio.to_thread(_try)
        assert event["type"] == "inbox_event"
        assert event["event"] == "session.claimed"
        assert event["data"]["session_id"] == 42

    async def test_excludes_emitter(self, client, staff_user, manager_user):
        """Emisor (staff) no debe recibir su propio evento."""
        staff_token = _token_for(staff_user)
        mgr_token = _token_for(manager_user)
        staff_uid = staff_user.id
        loop = asyncio.get_event_loop()

        def _try():
            with client.websocket_connect(
                f"/api/v1/inbox/ws?token={staff_token}"
            ) as a, client.websocket_connect(
                f"/api/v1/inbox/ws?token={mgr_token}"
            ) as b:
                a.receive_json()  # hello
                b.receive_json()  # hello
                fut = asyncio.run_coroutine_threadsafe(
                    inbox_ws.publish_event(
                        "session.claimed",
                        {"session_id": 7},
                        exclude_user_id=staff_uid,
                    ),
                    loop,
                )
                sent = fut.result(timeout=2.0)
                # Solo el manager recibe
                mgr_evt = b.receive_json()
                return sent, mgr_evt, a

        sent, mgr_evt, _a = await asyncio.to_thread(_try)
        assert sent == 1
        assert mgr_evt["event"] == "session.claimed"

    async def test_multiple_tabs_same_user_both_receive(
        self, client, staff_user
    ):
        token = _token_for(staff_user)
        loop = asyncio.get_event_loop()

        def _try():
            with client.websocket_connect(
                f"/api/v1/inbox/ws?token={token}"
            ) as a, client.websocket_connect(
                f"/api/v1/inbox/ws?token={token}"
            ) as b:
                a.receive_json()  # hello
                b.receive_json()  # hello
                fut = asyncio.run_coroutine_threadsafe(
                    inbox_ws.publish_event(
                        "session.released", {"session_id": 11}
                    ),
                    loop,
                )
                sent = fut.result(timeout=2.0)
                evt_a = a.receive_json()
                evt_b = b.receive_json()
                return sent, evt_a, evt_b

        sent, evt_a, evt_b = await asyncio.to_thread(_try)
        assert sent == 2
        assert evt_a["event"] == "session.released"
        assert evt_b["event"] == "session.released"

    async def test_clean_disconnect_unregisters(self, client, staff_user):
        token = _token_for(staff_user)

        def _try():
            with client.websocket_connect(
                f"/api/v1/inbox/ws?token={token}"
            ) as ws:
                ws.receive_json()  # hello
            # Fuera del context: desconectado.

        await asyncio.to_thread(_try)
        # Dar tiempo al cleanup async del endpoint
        for _ in range(20):
            if inbox_ws.total_sockets_count() == 0:
                break
            await asyncio.sleep(0.05)
        assert inbox_ws.total_sockets_count() == 0
