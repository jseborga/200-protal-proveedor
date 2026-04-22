"""Tests HTTP del endpoint POST /api/v1/inbox/sessions/{id}/send.

Usa FastAPI TestClient con dependency_overrides para:
- Sustituir get_db por la sesion SQLite in-memory del conftest
- Sustituir require_staff por un usuario staff de prueba

Mockea send_whatsapp/send_telegram para no llamar servicios externos.
"""
import os
# El engine real no se usa (dependency_overrides sustituye get_db por la
# sesion SQLite in-memory del conftest).
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import require_staff, require_manager
from app.core.database import get_db
from app.api.routes.inbox import router as inbox_router
from app.models.user import User


@pytest_asyncio.fixture
async def staff_user(db) -> User:
    u = User(
        email="staff@test.com",
        hashed_password="x",
        full_name="Staff Tester",
        role="manager",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def app(db, staff_user):
    """FastAPI app montando solo el router de inbox con overrides de deps."""
    app = FastAPI()
    app.include_router(inbox_router, prefix="/api/v1/inbox")

    async def _get_db_override():
        # Reusa la misma sesion que los fixtures para ver cambios
        yield db

    async def _require_staff_override():
        return staff_user

    async def _require_manager_override():
        return staff_user

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[require_staff] = _require_staff_override
    app.dependency_overrides[require_manager] = _require_manager_override
    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def mock_messaging():
    """Evita llamadas a Evolution/TG."""
    with patch("app.services.conversation_hub.send_whatsapp", new=AsyncMock(return_value=True)) as wa, \
         patch("app.services.conversation_hub.send_telegram", new=AsyncMock(return_value=True)) as tg_hub, \
         patch("app.services.messaging.send_telegram", new=AsyncMock(return_value=True)) as tg_msg:
        yield {"wa": wa, "tg_hub": tg_hub, "tg_msg": tg_msg}


# ── POST /sessions/{id}/send ──────────────────────────────────────
class TestInboxSendEndpoint:
    async def test_send_success_within_window(self, client, db, sample_session, mock_messaging):
        sample_session.state = "active"
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()

        resp = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/send",
            json={"text": "Hola, te cotizo"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["mode"] == "whatsapp"
        mock_messaging["wa"].assert_called_once()
        # El phone pasado al servicio WA
        args = mock_messaging["wa"].call_args[0]
        assert args[0] == "59171234567"
        assert args[1] == "Hola, te cotizo"

    async def test_send_fails_window_closed(self, client, db, sample_session, mock_messaging):
        sample_session.state = "active"
        sample_session.last_client_msg_at = datetime.now(timezone.utc) - timedelta(hours=48)
        await db.commit()

        resp = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/send",
            json={"text": "mensaje tarde"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["mode"] == "window_closed"
        mock_messaging["wa"].assert_not_called()

    async def test_send_fails_session_closed(self, client, db, sample_session, mock_messaging):
        sample_session.state = "closed"
        await db.commit()

        resp = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/send",
            json={"text": "hola"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["mode"] == "closed"
        mock_messaging["wa"].assert_not_called()

    async def test_send_fails_no_phone(self, client, db, sample_session, mock_messaging):
        sample_session.state = "active"
        sample_session.client_phone = None
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()

        resp = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/send",
            json={"text": "hola"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["mode"] == "no_phone"
        mock_messaging["wa"].assert_not_called()

    async def test_send_404_for_unknown_session(self, client, mock_messaging):
        resp = await client.post(
            "/api/v1/inbox/sessions/999999/send",
            json={"text": "hola"},
        )
        assert resp.status_code == 404

    async def test_send_422_empty_text(self, client, sample_session, db, mock_messaging):
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()
        resp = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/send",
            json={"text": ""},
        )
        assert resp.status_code == 422  # pydantic min_length=1

    async def test_send_422_text_too_long(self, client, sample_session, db, mock_messaging):
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()
        resp = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/send",
            json={"text": "x" * 5000},  # max_length=4000
        )
        assert resp.status_code == 422

    async def test_send_mirrors_to_telegram_topic(self, client, db, sample_session, mock_messaging):
        sample_session.state = "active"
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        sample_session.tg_group_id = "-100123"
        sample_session.tg_topic_id = 42
        await db.commit()

        resp = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/send",
            json={"text": "Respuesta desde web"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        # WA al cliente
        mock_messaging["wa"].assert_called_once()
        # Mirror al topic via messaging.send_telegram
        mock_messaging["tg_msg"].assert_called_once()
        tg_args = mock_messaging["tg_msg"].call_args
        assert tg_args[0][0] == "-100123"
        # El texto enviado al topic contiene el nombre del operador
        assert "Staff Tester" in tg_args[0][1]
        assert "Respuesta desde web" in tg_args[0][1]

    async def test_send_persists_outbound_message(self, client, db, sample_session, mock_messaging):
        sample_session.state = "active"
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()

        resp = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/send",
            json={"text": "queda registrado"},
        )
        assert resp.status_code == 200

        # Fetch messages de la sesion
        from sqlalchemy import select
        from app.models.conversation import Message
        msgs = (await db.execute(
            select(Message).where(Message.session_id == sample_session.id)
        )).scalars().all()
        outbound = [m for m in msgs if m.direction == "outbound"]
        assert len(outbound) == 1
        assert outbound[0].sender_type == "operator"
        assert outbound[0].body == "queda registrado"
        assert outbound[0].channel == "whatsapp"


# ── GET /sessions/{id} y /sessions ────────────────────────────────
class TestInboxReadEndpoints:
    async def test_get_session_detail(self, client, db, sample_session, mock_messaging):
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()

        resp = await client.get(f"/api/v1/inbox/sessions/{sample_session.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["id"] == sample_session.id
        assert data["pedido_ref"] == "PED-0001"
        assert data["client_phone"] == "59171234567"
        assert data["wa_window"]["open"] is True
        assert "messages" in data

    async def test_get_session_404(self, client, mock_messaging):
        resp = await client.get("/api/v1/inbox/sessions/999999")
        assert resp.status_code == 404

    async def test_list_sessions(self, client, db, sample_session, mock_messaging):
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()

        resp = await client.get("/api/v1/inbox/sessions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["total"] >= 1
        assert len(body["data"]) >= 1
        assert body["data"][0]["id"] == sample_session.id

    async def test_list_sessions_unread_only(self, client, db, sample_session, mock_messaging):
        # Cliente escribio, operador no respondio → unread
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        sample_session.last_operator_msg_at = None
        sample_session.state = "active"
        await db.commit()

        resp = await client.get("/api/v1/inbox/sessions?unread_only=true")
        assert resp.status_code == 200
        body = resp.json()
        assert any(s["id"] == sample_session.id for s in body["data"])
        # Todas las devueltas deben estar unread
        for s in body["data"]:
            assert s["unread"] is True

    async def test_list_sessions_state_filter(self, client, db, sample_session, mock_messaging):
        sample_session.state = "operator_engaged"
        await db.commit()

        resp = await client.get("/api/v1/inbox/sessions?state=operator_engaged")
        assert resp.status_code == 200
        body = resp.json()
        assert all(s["state"] == "operator_engaged" for s in body["data"])


# ── POST claim/release/assign ─────────────────────────────────────
class TestInboxAssignEndpoints:
    async def test_claim_unassigned(self, client, db, sample_session, staff_user, mock_messaging):
        assert sample_session.operator_id is None
        resp = await client.post(f"/api/v1/inbox/sessions/{sample_session.id}/claim")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["operator_id"] == staff_user.id

    async def test_claim_conflict_other_operator(self, client, db, sample_session, staff_user, mock_messaging):
        # Asignar a otro operador primero
        other = User(
            email="otro@test.com", hashed_password="x", full_name="Otro",
            role="field_agent", is_active=True,
        )
        db.add(other)
        await db.commit()
        sample_session.operator_id = other.id
        await db.commit()

        # staff_user es manager, asi que puede reasignar (no hay conflicto)
        resp = await client.post(f"/api/v1/inbox/sessions/{sample_session.id}/claim")
        assert resp.status_code == 200
        body = resp.json()
        # Como el staff es manager, reasigna
        assert body["ok"] is True
        assert body["operator_id"] == staff_user.id

    async def test_release_own_session(self, client, db, sample_session, staff_user, mock_messaging):
        sample_session.operator_id = staff_user.id
        await db.commit()

        resp = await client.post(f"/api/v1/inbox/sessions/{sample_session.id}/release")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["operator_id"] is None

    async def test_assign_requires_manager(self, client, db, sample_session, staff_user, mock_messaging):
        # staff_user es manager (fixture)
        new_op = User(
            email="op@test.com", hashed_password="x", full_name="Op",
            role="field_agent", is_active=True,
        )
        db.add(new_op)
        await db.commit()

        resp = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/assign",
            json={"operator_id": new_op.id},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["operator_id"] == new_op.id

    async def test_assign_rejects_non_staff(self, client, db, sample_session, mock_messaging):
        # Crear user 'buyer' — no esta en STAFF_ROLES
        buyer = User(
            email="buyer@test.com", hashed_password="x", full_name="Buyer",
            role="buyer", is_active=True,
        )
        db.add(buyer)
        await db.commit()

        resp = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/assign",
            json={"operator_id": buyer.id},
        )
        assert resp.status_code == 400  # "no es staff activo"
