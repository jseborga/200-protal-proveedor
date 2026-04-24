"""Tests HTTP de la Fase 5.12: tags/etiquetas manuales sobre sesiones.

Cubre:
- CRUD del catalogo global de tags (GET/POST/PATCH/DELETE /inbox/tags).
- Assign/unassign de tags a sesiones (POST/DELETE /inbox/sessions/{id}/tags).
- Serializacion de `tags` en respuestas de listado y detalle de sesion.
- Filtro `?tags=1,2` (interseccion).
- usage_count ordenado correctamente.
- Permisos: require_manager en mutaciones.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.api.deps import require_staff, require_manager
from app.core.database import get_db
from app.api.routes.inbox import router as inbox_router
from app.models.conversation import ConversationSession
from app.models.pedido import Pedido
from app.models.session_tag import Tag, SessionTag
from app.models.user import User


# ── Fixtures ──────────────────────────────────────────────────
@pytest_asyncio.fixture
async def engine_with_tags(engine):
    """Extiende el engine del conftest con mkt_tag y mkt_session_tag."""
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Tag.__table__.create(sync_conn, checkfirst=True)
        )
        await conn.run_sync(
            lambda sync_conn: SessionTag.__table__.create(sync_conn, checkfirst=True)
        )
    yield engine


@pytest_asyncio.fixture
async def db(engine_with_tags):
    """Override del fixture db para usar engine_with_tags."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    Session = async_sessionmaker(
        engine_with_tags, expire_on_commit=False, class_=AsyncSession,
    )
    async with Session() as session:
        yield session


@pytest_asyncio.fixture
async def manager_user(db) -> User:
    u = User(
        email="mgr@test.com",
        hashed_password="x",
        full_name="Manager",
        role="manager",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def agent_user(db) -> User:
    u = User(
        email="agent@test.com",
        hashed_password="x",
        full_name="Agent",
        role="field_agent",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _build_app(db, user_for_staff: User, user_for_manager: User | None):
    """Helper para armar la app con overrides configurables."""
    app = FastAPI()
    app.include_router(inbox_router, prefix="/api/v1/inbox")

    async def _get_db_override():
        yield db

    async def _require_staff_override():
        return user_for_staff

    async def _require_manager_override():
        if user_for_manager is None:
            raise HTTPException(403, "Requiere rol manager")
        return user_for_manager

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[require_staff] = _require_staff_override
    app.dependency_overrides[require_manager] = _require_manager_override
    return app


@pytest_asyncio.fixture
async def app(db, manager_user):
    app = _build_app(db, manager_user, manager_user)
    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def app_agent(db, agent_user):
    """App donde require_manager falla (agent user)."""
    app = _build_app(db, agent_user, None)
    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_agent(app_agent):
    transport = ASGITransport(app=app_agent)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def sample_pedido(db, manager_user) -> Pedido:
    p = Pedido(
        reference="PED-TAG",
        title="Pedido de prueba tags",
        state="active",
        created_by=manager_user.id,
        currency="BOB",
        item_count=0,
        quotes_received=0,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


@pytest_asyncio.fixture
async def sample_session(db, sample_pedido) -> ConversationSession:
    s = ConversationSession(
        pedido_id=sample_pedido.id,
        client_phone="59170000001",
        state="active",
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest_asyncio.fixture
async def other_session(db, sample_pedido) -> ConversationSession:
    s = ConversationSession(
        pedido_id=sample_pedido.id,
        client_phone="59170000002",
        state="active",
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


# ── TestTagCRUD ───────────────────────────────────────────────
class TestTagCRUD:
    async def test_create_tag(self, client):
        resp = await client.post(
            "/api/v1/inbox/tags",
            json={"name": "VIP", "color": "red"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["created"] is True
        assert body["data"]["name"] == "vip"  # normalizado a lowercase
        assert body["data"]["color"] == "red"
        assert isinstance(body["data"]["id"], int)

    async def test_create_tag_dedupes_case_insensitive(self, client):
        r1 = await client.post(
            "/api/v1/inbox/tags",
            json={"name": "lead_frio", "color": "blue"},
        )
        assert r1.status_code == 200
        id1 = r1.json()["data"]["id"]

        r2 = await client.post(
            "/api/v1/inbox/tags",
            json={"name": "  LEAD_FRIO  ", "color": "green"},
        )
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["created"] is False
        assert body2["data"]["id"] == id1
        assert body2["data"]["color"] == "blue"  # no recolorea

    async def test_create_tag_invalid_color(self, client):
        resp = await client.post(
            "/api/v1/inbox/tags",
            json={"name": "test", "color": "fuchsia"},
        )
        assert resp.status_code == 400

    async def test_create_tag_requires_manager(self, client_agent):
        resp = await client_agent.post(
            "/api/v1/inbox/tags",
            json={"name": "x", "color": "slate"},
        )
        assert resp.status_code == 403

    async def test_update_tag_rename(self, client):
        r = await client.post(
            "/api/v1/inbox/tags", json={"name": "foo", "color": "slate"},
        )
        tid = r.json()["data"]["id"]
        r2 = await client.patch(
            f"/api/v1/inbox/tags/{tid}",
            json={"name": "bar", "color": "purple"},
        )
        assert r2.status_code == 200
        assert r2.json()["data"]["name"] == "bar"
        assert r2.json()["data"]["color"] == "purple"

    async def test_update_tag_name_collision(self, client):
        a = await client.post(
            "/api/v1/inbox/tags", json={"name": "alpha", "color": "slate"},
        )
        b = await client.post(
            "/api/v1/inbox/tags", json={"name": "beta", "color": "slate"},
        )
        bid = b.json()["data"]["id"]
        r = await client.patch(
            f"/api/v1/inbox/tags/{bid}",
            json={"name": "ALPHA"},
        )
        assert r.status_code == 400

    async def test_update_tag_not_found(self, client):
        r = await client.patch(
            "/api/v1/inbox/tags/9999",
            json={"name": "x"},
        )
        assert r.status_code == 404

    async def test_delete_tag(self, client, db):
        r = await client.post(
            "/api/v1/inbox/tags", json={"name": "temp", "color": "yellow"},
        )
        tid = r.json()["data"]["id"]
        r2 = await client.delete(f"/api/v1/inbox/tags/{tid}")
        assert r2.status_code == 200
        assert r2.json()["ok"] is True
        # GET no devuelve la tag
        r3 = await client.get("/api/v1/inbox/tags")
        names = [t["name"] for t in r3.json()["data"]]
        assert "temp" not in names

    async def test_delete_tag_requires_manager(self, client_agent):
        resp = await client_agent.delete("/api/v1/inbox/tags/1")
        assert resp.status_code == 403

    async def test_list_tags_includes_usage_count(
        self, client, db, sample_session, other_session
    ):
        t1 = (await client.post(
            "/api/v1/inbox/tags", json={"name": "alpha", "color": "slate"},
        )).json()["data"]
        t2 = (await client.post(
            "/api/v1/inbox/tags", json={"name": "beta", "color": "blue"},
        )).json()["data"]
        # alpha a dos sesiones, beta a una
        await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": t1["id"]},
        )
        await client.post(
            f"/api/v1/inbox/sessions/{other_session.id}/tags",
            json={"tag_id": t1["id"]},
        )
        await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": t2["id"]},
        )
        r = await client.get("/api/v1/inbox/tags")
        data = r.json()["data"]
        by_name = {t["name"]: t for t in data}
        assert by_name["alpha"]["usage_count"] == 2
        assert by_name["beta"]["usage_count"] == 1
        # Orden DESC por usage_count: alpha antes que beta
        assert data[0]["name"] == "alpha"


# ── TestSessionTagAssign ──────────────────────────────────────
class TestSessionTagAssign:
    async def test_assign_by_id(self, client, sample_session):
        t = (await client.post(
            "/api/v1/inbox/tags", json={"name": "urgent", "color": "red"},
        )).json()["data"]
        r = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": t["id"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["already"] is False
        assert body["data"]["id"] == t["id"]

    async def test_assign_by_name_creates_tag(self, client, sample_session):
        r = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"name": "mayorista", "color": "purple"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["name"] == "mayorista"
        assert body["data"]["color"] == "purple"
        # Se listo en catalogo
        cat = (await client.get("/api/v1/inbox/tags")).json()["data"]
        assert any(t["name"] == "mayorista" for t in cat)

    async def test_assign_dedupe_silent(self, client, sample_session):
        t = (await client.post(
            "/api/v1/inbox/tags", json={"name": "dup", "color": "slate"},
        )).json()["data"]
        r1 = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": t["id"]},
        )
        assert r1.json()["already"] is False
        r2 = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": t["id"]},
        )
        assert r2.status_code == 200
        assert r2.json()["already"] is True

    async def test_assign_missing_session(self, client):
        r = await client.post(
            "/api/v1/inbox/sessions/9999/tags",
            json={"name": "x", "color": "slate"},
        )
        assert r.status_code == 404

    async def test_assign_missing_tag_id(self, client, sample_session):
        r = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": 9999},
        )
        assert r.status_code == 404

    async def test_assign_requires_name_or_id(self, client, sample_session):
        r = await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={},
        )
        assert r.status_code == 400

    async def test_assign_requires_manager(
        self, client_agent, db, sample_session
    ):
        # Crear tag directo en DB para saltear POST /tags (que tambien require_manager)
        t = Tag(name="x", color="slate")
        db.add(t)
        await db.commit()
        await db.refresh(t)
        r = await client_agent.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": t.id},
        )
        assert r.status_code == 403

    async def test_unassign(self, client, sample_session):
        t = (await client.post(
            "/api/v1/inbox/tags", json={"name": "rm", "color": "slate"},
        )).json()["data"]
        await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": t["id"]},
        )
        r = await client.delete(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags/{t['id']}"
        )
        assert r.status_code == 200
        assert r.json()["removed"] is True

    async def test_unassign_idempotent(self, client, sample_session):
        t = (await client.post(
            "/api/v1/inbox/tags", json={"name": "rm2", "color": "slate"},
        )).json()["data"]
        r = await client.delete(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags/{t['id']}"
        )
        assert r.status_code == 200
        assert r.json()["removed"] is False


# ── TestSessionSerialization ──────────────────────────────────
class TestSessionSerialization:
    async def test_list_sessions_includes_tags(
        self, client, sample_session, other_session
    ):
        t1 = (await client.post(
            "/api/v1/inbox/tags", json={"name": "vip", "color": "red"},
        )).json()["data"]
        t2 = (await client.post(
            "/api/v1/inbox/tags", json={"name": "mayorista", "color": "blue"},
        )).json()["data"]
        await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": t1["id"]},
        )
        await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": t2["id"]},
        )

        r = await client.get("/api/v1/inbox/sessions")
        assert r.status_code == 200
        sessions = r.json()["data"]
        sample_row = next(s for s in sessions if s["id"] == sample_session.id)
        other_row = next(s for s in sessions if s["id"] == other_session.id)
        assert len(sample_row["tags"]) == 2
        tag_names = sorted(t["name"] for t in sample_row["tags"])
        assert tag_names == ["mayorista", "vip"]
        # sesion sin tags trae lista vacia (no null)
        assert other_row["tags"] == []

    async def test_get_session_includes_tags(self, client, sample_session):
        t = (await client.post(
            "/api/v1/inbox/tags", json={"name": "detail", "color": "green"},
        )).json()["data"]
        await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": t["id"]},
        )
        r = await client.get(f"/api/v1/inbox/sessions/{sample_session.id}")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["tags"] == [
            {"id": t["id"], "name": "detail", "color": "green"}
        ]


# ── TestListFilter ────────────────────────────────────────────
class TestListFilter:
    async def test_filter_single_tag(
        self, client, sample_session, other_session
    ):
        t1 = (await client.post(
            "/api/v1/inbox/tags", json={"name": "f1", "color": "slate"},
        )).json()["data"]
        await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": t1["id"]},
        )
        r = await client.get(f"/api/v1/inbox/sessions?tags={t1['id']}")
        ids = [s["id"] for s in r.json()["data"]]
        assert sample_session.id in ids
        assert other_session.id not in ids

    async def test_filter_intersection(
        self, client, sample_session, other_session
    ):
        t1 = (await client.post(
            "/api/v1/inbox/tags", json={"name": "a", "color": "slate"},
        )).json()["data"]
        t2 = (await client.post(
            "/api/v1/inbox/tags", json={"name": "b", "color": "blue"},
        )).json()["data"]
        # sample tiene A+B; other solo A
        await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": t1["id"]},
        )
        await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": t2["id"]},
        )
        await client.post(
            f"/api/v1/inbox/sessions/{other_session.id}/tags",
            json={"tag_id": t1["id"]},
        )
        r = await client.get(
            f"/api/v1/inbox/sessions?tags={t1['id']},{t2['id']}"
        )
        ids = [s["id"] for s in r.json()["data"]]
        assert ids == [sample_session.id]

    async def test_filter_empty_intersection(
        self, client, sample_session, other_session
    ):
        t1 = (await client.post(
            "/api/v1/inbox/tags", json={"name": "x", "color": "slate"},
        )).json()["data"]
        t2 = (await client.post(
            "/api/v1/inbox/tags", json={"name": "y", "color": "blue"},
        )).json()["data"]
        await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": t1["id"]},
        )
        await client.post(
            f"/api/v1/inbox/sessions/{other_session.id}/tags",
            json={"tag_id": t2["id"]},
        )
        r = await client.get(
            f"/api/v1/inbox/sessions?tags={t1['id']},{t2['id']}"
        )
        assert r.json()["data"] == []

    async def test_filter_ignores_invalid_ids(self, client, sample_session):
        t = (await client.post(
            "/api/v1/inbox/tags", json={"name": "ok", "color": "slate"},
        )).json()["data"]
        await client.post(
            f"/api/v1/inbox/sessions/{sample_session.id}/tags",
            json={"tag_id": t["id"]},
        )
        r = await client.get(
            f"/api/v1/inbox/sessions?tags={t['id']},abc,,99999"
        )
        # 99999 existe como id pero sin sesiones -> interseccion vacia
        # con t + 99999 no deberia incluir sample
        assert r.json()["data"] == []

    async def test_no_filter_returns_all(
        self, client, sample_session, other_session
    ):
        r = await client.get("/api/v1/inbox/sessions")
        ids = {s["id"] for s in r.json()["data"]}
        assert sample_session.id in ids
        assert other_session.id in ids
