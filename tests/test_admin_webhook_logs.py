"""Tests HTTP de /admin/webhook-logs y /admin/webhook-logs/{id}.

Cubre:
- Filtros (source, event_type, instance_name, status)
- Paginacion (limit clamp 1..200, offset)
- Orden descendente por id (mas reciente primero)
- payload_preview (primeros 10 keys, no payload completo)
- Detail endpoint: devuelve payload completo + 404 si no existe
- Auth: sin require_admin override -> falla (401/403)
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Integer

from app.api.deps import require_admin
from app.core.database import get_db
from app.api.routes.admin import router as admin_router
from app.models.user import User
from app.models.webhook_log import WebhookLog


@pytest_asyncio.fixture
async def wh_engine_db(db):
    """Crea la tabla mkt_webhook_log en el engine del fixture `db`."""
    # Forzar INTEGER para autoincrement en SQLite
    WebhookLog.__table__.c.id.type = Integer()
    eng = db.bind
    async with eng.begin() as conn:
        await conn.run_sync(lambda sc: WebhookLog.__table__.create(sc, checkfirst=True))
    return db


@pytest_asyncio.fixture
async def admin_user(wh_engine_db) -> User:
    u = User(
        email="admin@test.com",
        hashed_password="x",
        full_name="Admin Tester",
        role="admin",
        is_active=True,
    )
    wh_engine_db.add(u)
    await wh_engine_db.commit()
    await wh_engine_db.refresh(u)
    return u


@pytest_asyncio.fixture
async def app(wh_engine_db, admin_user):
    app = FastAPI()
    app.include_router(admin_router, prefix="/admin")

    async def _get_db_override():
        yield wh_engine_db

    async def _require_admin_override():
        return admin_user

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[require_admin] = _require_admin_override
    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def sample_logs(wh_engine_db):
    """Inserta 6 rows mezclando sources/events/instances/status."""
    rows = [
        WebhookLog(source="whatsapp", event_type="messages.upsert",
                   instance_name="apu", status="received",
                   payload={"a": 1, "b": "x"}),
        WebhookLog(source="whatsapp", event_type="messages.upsert",
                   instance_name="ventas", status="received", payload={"c": 2}),
        WebhookLog(source="whatsapp", event_type="connection.update",
                   instance_name="apu", status="error", payload={},
                   error="boom"),
        WebhookLog(source="telegram", event_type="message",
                   instance_name=None, status="received",
                   payload={"update_id": 42}),
        WebhookLog(source="telegram", event_type="callback_query",
                   instance_name=None, status="processed", payload={}),
        WebhookLog(source="whatsapp", event_type="messages.upsert",
                   instance_name="apu", status="received",
                   payload={"latest": True}),
    ]
    for r in rows:
        wh_engine_db.add(r)
    await wh_engine_db.commit()
    for r in rows:
        await wh_engine_db.refresh(r)
    return rows


class TestListWebhookLogs:
    async def test_no_filters_returns_all_desc(self, client, sample_logs):
        resp = await client.get("/admin/webhook-logs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["total"] == 6
        assert data["offset"] == 0
        # default limit = 50
        assert data["limit"] == 50
        ids = [i["id"] for i in data["items"]]
        # orden descendente por id
        assert ids == sorted(ids, reverse=True)

    async def test_filter_by_source_whatsapp(self, client, sample_logs):
        resp = await client.get("/admin/webhook-logs?source=whatsapp")
        body = resp.json()
        assert body["data"]["total"] == 4
        for item in body["data"]["items"]:
            assert item["source"] == "whatsapp"

    async def test_filter_by_source_telegram(self, client, sample_logs):
        resp = await client.get("/admin/webhook-logs?source=telegram")
        body = resp.json()
        assert body["data"]["total"] == 2
        for item in body["data"]["items"]:
            assert item["source"] == "telegram"

    async def test_filter_by_event_type(self, client, sample_logs):
        resp = await client.get("/admin/webhook-logs?event_type=messages.upsert")
        body = resp.json()
        assert body["data"]["total"] == 3
        for item in body["data"]["items"]:
            assert item["event_type"] == "messages.upsert"

    async def test_filter_by_instance_name(self, client, sample_logs):
        resp = await client.get("/admin/webhook-logs?instance_name=apu")
        body = resp.json()
        assert body["data"]["total"] == 3
        for item in body["data"]["items"]:
            assert item["instance_name"] == "apu"

    async def test_filter_by_status_error(self, client, sample_logs):
        resp = await client.get("/admin/webhook-logs?status=error")
        body = resp.json()
        assert body["data"]["total"] == 1
        item = body["data"]["items"][0]
        assert item["status"] == "error"
        assert item["error"] == "boom"

    async def test_combined_filters(self, client, sample_logs):
        resp = await client.get(
            "/admin/webhook-logs?source=whatsapp&instance_name=apu&status=received"
        )
        body = resp.json()
        # 2 rows: messages.upsert#1 y messages.upsert#latest
        assert body["data"]["total"] == 2
        for item in body["data"]["items"]:
            assert item["source"] == "whatsapp"
            assert item["instance_name"] == "apu"
            assert item["status"] == "received"

    async def test_pagination_limit_and_offset(self, client, sample_logs):
        r1 = await client.get("/admin/webhook-logs?limit=2&offset=0")
        r2 = await client.get("/admin/webhook-logs?limit=2&offset=2")
        r3 = await client.get("/admin/webhook-logs?limit=2&offset=4")
        b1, b2, b3 = r1.json(), r2.json(), r3.json()
        assert b1["data"]["total"] == b2["data"]["total"] == b3["data"]["total"] == 6
        assert len(b1["data"]["items"]) == 2
        assert len(b2["data"]["items"]) == 2
        assert len(b3["data"]["items"]) == 2
        all_ids = (
            [i["id"] for i in b1["data"]["items"]]
            + [i["id"] for i in b2["data"]["items"]]
            + [i["id"] for i in b3["data"]["items"]]
        )
        # Todos distintos y en orden desc
        assert len(set(all_ids)) == 6
        assert all_ids == sorted(all_ids, reverse=True)

    async def test_limit_clamp_upper(self, client, sample_logs):
        resp = await client.get("/admin/webhook-logs?limit=999")
        body = resp.json()
        assert body["data"]["limit"] == 200

    async def test_limit_clamp_lower(self, client, sample_logs):
        resp = await client.get("/admin/webhook-logs?limit=0")
        body = resp.json()
        assert body["data"]["limit"] == 1

    async def test_offset_negative_clamped(self, client, sample_logs):
        resp = await client.get("/admin/webhook-logs?offset=-5")
        body = resp.json()
        assert body["data"]["offset"] == 0

    async def test_payload_preview_not_full_payload(self, client, wh_engine_db):
        # payload con muchos keys y valores largos
        big_payload = {f"k{i}": "x" * 500 for i in range(20)}
        wh_engine_db.add(WebhookLog(
            source="whatsapp", event_type="e",
            instance_name="apu", status="received", payload=big_payload,
        ))
        await wh_engine_db.commit()
        resp = await client.get("/admin/webhook-logs?source=whatsapp")
        body = resp.json()
        item = body["data"]["items"][0]
        prev = item["payload_preview"]
        # Maximo 10 keys
        assert len(prev) <= 10
        # Valores truncados a 80 chars
        for v in prev.values():
            assert isinstance(v, str)
            assert len(v) <= 80

    async def test_empty_result(self, client, sample_logs):
        resp = await client.get("/admin/webhook-logs?instance_name=noexiste")
        body = resp.json()
        assert body["data"]["total"] == 0
        assert body["data"]["items"] == []


class TestGetWebhookLogDetail:
    async def test_returns_full_payload(self, client, sample_logs):
        # Tomar el id del ultimo insertado
        target = sample_logs[-1]
        resp = await client.get(f"/admin/webhook-logs/{target.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        d = body["data"]
        assert d["id"] == target.id
        assert d["source"] == "whatsapp"
        # Payload completo presente
        assert d["payload"] == {"latest": True}

    async def test_404_when_not_found(self, client, sample_logs):
        resp = await client.get("/admin/webhook-logs/999999")
        assert resp.status_code == 404


class TestAuthRequired:
    async def test_requires_admin(self, wh_engine_db, sample_logs):
        """Sin override de require_admin, endpoint rechaza la request."""
        app = FastAPI()
        app.include_router(admin_router, prefix="/admin")

        async def _get_db_override():
            yield wh_engine_db

        app.dependency_overrides[get_db] = _get_db_override
        # NO overridear require_admin -> la dep real intentara validar

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/admin/webhook-logs")
        # Sin JWT/API key valido, require_admin debe rechazar
        assert resp.status_code in (401, 403)
