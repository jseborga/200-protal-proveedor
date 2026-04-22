"""Tests de los endpoints Web Push / VAPID del inbox (5.5).

Cubre:
- /inbox/push/vapid-public-key (configurado / no configurado)
- /inbox/push/subscribe (insert + upsert + auth)
- /inbox/push/unsubscribe (owner vs otro user + manager)
- /inbox/push/test (sin VAPID devuelve delivered=0)
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Integer, select

from app.api.deps import require_staff
from app.core.config import settings
from app.core.database import get_db
from app.api.routes.inbox import router as inbox_router
from app.models.push_subscription import PushSubscription
from app.models.user import User


@pytest_asyncio.fixture
async def push_engine_db(db):
    """Crea mkt_push_subscription en el engine del fixture db."""
    PushSubscription.__table__.c.id.type = Integer()
    eng = db.bind
    async with eng.begin() as conn:
        await conn.run_sync(
            lambda sc: PushSubscription.__table__.create(sc, checkfirst=True)
        )
    return db


@pytest_asyncio.fixture
async def staff_user(push_engine_db) -> User:
    u = User(
        email="staff@test.com",
        hashed_password="x",
        full_name="Staff Tester",
        role="manager",
        is_active=True,
    )
    push_engine_db.add(u)
    await push_engine_db.commit()
    await push_engine_db.refresh(u)
    return u


@pytest_asyncio.fixture
async def other_user(push_engine_db) -> User:
    u = User(
        email="other@test.com",
        hashed_password="x",
        full_name="Other",
        role="field_agent",
        is_active=True,
    )
    push_engine_db.add(u)
    await push_engine_db.commit()
    await push_engine_db.refresh(u)
    return u


def _build_app(db, acting_user: User) -> FastAPI:
    app = FastAPI()
    app.include_router(inbox_router, prefix="/api/v1/inbox")

    async def _get_db_override():
        yield db

    async def _require_staff_override():
        return acting_user

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[require_staff] = _require_staff_override
    return app


@pytest_asyncio.fixture
async def client(push_engine_db, staff_user):
    app = _build_app(push_engine_db, staff_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


class TestVapidPublicKey:
    async def test_returns_disabled_when_not_configured(self, client):
        # Limpiar la clave
        orig = settings.vapid_public_key
        settings.vapid_public_key = ""
        try:
            resp = await client.get("/api/v1/inbox/push/vapid-public-key")
            assert resp.status_code == 200
            body = resp.json()
            assert body["ok"] is True
            assert body["enabled"] is False
            assert body["public_key"] is None
        finally:
            settings.vapid_public_key = orig

    async def test_returns_key_when_configured(self, client):
        orig = settings.vapid_public_key
        settings.vapid_public_key = "BK-FAKE-KEY"
        try:
            resp = await client.get("/api/v1/inbox/push/vapid-public-key")
            body = resp.json()
            assert body["enabled"] is True
            assert body["public_key"] == "BK-FAKE-KEY"
        finally:
            settings.vapid_public_key = orig


class TestSubscribe:
    async def test_create_new_subscription(
        self, client, push_engine_db, staff_user
    ):
        resp = await client.post(
            "/api/v1/inbox/push/subscribe",
            json={
                "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
                "keys": {"p256dh": "P256KEY", "auth": "AUTHKEY"},
                "user_agent": "TestBrowser/1.0",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["updated"] is False
        assert "id" in body

        row = (await push_engine_db.execute(
            select(PushSubscription).where(
                PushSubscription.endpoint == "https://fcm.googleapis.com/fcm/send/abc"
            )
        )).scalar_one()
        assert row.user_id == staff_user.id
        assert row.p256dh == "P256KEY"
        assert row.auth == "AUTHKEY"
        assert row.user_agent == "TestBrowser/1.0"

    async def test_upsert_existing_endpoint(
        self, client, push_engine_db, staff_user
    ):
        existing = PushSubscription(
            user_id=staff_user.id,
            endpoint="https://ep/1",
            p256dh="OLD", auth="OLDAUTH",
        )
        push_engine_db.add(existing)
        await push_engine_db.commit()

        resp = await client.post(
            "/api/v1/inbox/push/subscribe",
            json={
                "endpoint": "https://ep/1",
                "keys": {"p256dh": "NEW", "auth": "NEWAUTH"},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] is True

        await push_engine_db.refresh(existing)
        assert existing.p256dh == "NEW"
        assert existing.auth == "NEWAUTH"

    async def test_rejects_without_keys(self, client):
        resp = await client.post(
            "/api/v1/inbox/push/subscribe",
            json={"endpoint": "https://x/y"},
        )
        assert resp.status_code == 422


class TestUnsubscribe:
    async def test_owner_can_unsubscribe(
        self, client, push_engine_db, staff_user
    ):
        sub = PushSubscription(
            user_id=staff_user.id,
            endpoint="https://ep/del",
            p256dh="a", auth="b",
        )
        push_engine_db.add(sub)
        await push_engine_db.commit()

        resp = await client.post(
            "/api/v1/inbox/push/unsubscribe",
            json={"endpoint": "https://ep/del"},
        )
        assert resp.status_code == 200
        assert resp.json()["removed"] is True

        row = (await push_engine_db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == "https://ep/del")
        )).scalar_one_or_none()
        assert row is None

    async def test_unsubscribe_unknown_returns_false(self, client):
        resp = await client.post(
            "/api/v1/inbox/push/unsubscribe",
            json={"endpoint": "https://does-not-exist"},
        )
        assert resp.status_code == 200
        assert resp.json()["removed"] is False

    async def test_non_owner_non_manager_rejected(
        self, push_engine_db, staff_user, other_user
    ):
        # other_user es field_agent; creamos una sub del staff_user (manager)
        # y el other intenta borrarla => 403 (no es owner, no es manager)
        sub = PushSubscription(
            user_id=staff_user.id,
            endpoint="https://ep/stolen",
            p256dh="a", auth="b",
        )
        push_engine_db.add(sub)
        await push_engine_db.commit()

        app = _build_app(push_engine_db, other_user)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/inbox/push/unsubscribe",
                json={"endpoint": "https://ep/stolen"},
            )
        assert resp.status_code == 403
        app.dependency_overrides.clear()

    async def test_manager_can_unsubscribe_anyones(
        self, client, push_engine_db, other_user
    ):
        # staff_user es manager. Debe poder eliminar sub de other_user.
        sub = PushSubscription(
            user_id=other_user.id,
            endpoint="https://ep/mgr",
            p256dh="a", auth="b",
        )
        push_engine_db.add(sub)
        await push_engine_db.commit()

        resp = await client.post(
            "/api/v1/inbox/push/unsubscribe",
            json={"endpoint": "https://ep/mgr"},
        )
        assert resp.status_code == 200
        assert resp.json()["removed"] is True


class TestPushTest:
    async def test_test_endpoint_without_vapid_returns_zero(
        self, client, push_engine_db, staff_user
    ):
        # Asegurar que VAPID no este configurado
        orig_pub = settings.vapid_public_key
        orig_priv = settings.vapid_private_key
        settings.vapid_public_key = ""
        settings.vapid_private_key = ""

        # Crear una sub cualquiera
        sub = PushSubscription(
            user_id=staff_user.id,
            endpoint="https://ep/test",
            p256dh="a", auth="b",
        )
        push_engine_db.add(sub)
        await push_engine_db.commit()

        try:
            resp = await client.post("/api/v1/inbox/push/test")
            assert resp.status_code == 200
            body = resp.json()
            assert body["ok"] is True
            assert body["delivered"] == 0
        finally:
            settings.vapid_public_key = orig_pub
            settings.vapid_private_key = orig_priv


class TestAuthRequired:
    async def test_endpoints_require_staff(self, push_engine_db):
        app = FastAPI()
        app.include_router(inbox_router, prefix="/api/v1/inbox")

        async def _get_db_override():
            yield push_engine_db

        app.dependency_overrides[get_db] = _get_db_override

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            for method, url, body in [
                ("GET", "/api/v1/inbox/push/vapid-public-key", None),
                ("POST", "/api/v1/inbox/push/subscribe",
                 {"endpoint": "x", "keys": {"p256dh": "a", "auth": "b"}}),
                ("POST", "/api/v1/inbox/push/unsubscribe", {"endpoint": "x"}),
                ("POST", "/api/v1/inbox/push/test", None),
            ]:
                if method == "GET":
                    r = await c.get(url)
                elif body is None:
                    r = await c.post(url)
                else:
                    r = await c.post(url, json=body)
                assert r.status_code in (401, 403), f"{method} {url} => {r.status_code}"
