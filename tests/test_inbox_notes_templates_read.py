"""Tests para Conversation Hub Fase 5:
- 5.3: /sessions/{id}/note (notas internas)
- 5.4: /templates CRUD con scope global/personal + RBAC
- 5.6: /sessions/{id}/mark-read + efecto en _is_unread / unread_count
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from datetime import datetime, timezone, timedelta

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Integer, select

from app.api.deps import require_staff, require_manager
from app.core.database import get_db
from app.api.routes.inbox import router as inbox_router
from app.models.conversation import ConversationSession, Message
from app.models.user import User
from app.models.pedido import Pedido
from app.models.inbox_template import InboxTemplate


# ── Fixtures ──────────────────────────────────────────────────
@pytest_asyncio.fixture
async def tpl_engine_db(db):
    """Crea la tabla mkt_inbox_template en el engine del fixture `db`."""
    # Forzar INTEGER para autoincrement en SQLite
    InboxTemplate.__table__.c.id.type = Integer()
    eng = db.bind
    async with eng.begin() as conn:
        await conn.run_sync(lambda sc: InboxTemplate.__table__.create(sc, checkfirst=True))
    return db


@pytest_asyncio.fixture
async def manager_user(tpl_engine_db) -> User:
    u = User(
        email="mgr@test.com",
        hashed_password="x",
        full_name="Manager Tester",
        role="manager",
        is_active=True,
    )
    tpl_engine_db.add(u)
    await tpl_engine_db.commit()
    await tpl_engine_db.refresh(u)
    return u


@pytest_asyncio.fixture
async def agent_user(tpl_engine_db) -> User:
    u = User(
        email="agent@test.com",
        hashed_password="x",
        full_name="Agent Tester",
        role="field_agent",
        is_active=True,
    )
    tpl_engine_db.add(u)
    await tpl_engine_db.commit()
    await tpl_engine_db.refresh(u)
    return u


@pytest_asyncio.fixture
async def other_agent(tpl_engine_db) -> User:
    u = User(
        email="other@test.com",
        hashed_password="x",
        full_name="Other Agent",
        role="field_agent",
        is_active=True,
    )
    tpl_engine_db.add(u)
    await tpl_engine_db.commit()
    await tpl_engine_db.refresh(u)
    return u


def _build_app(db, acting_user: User) -> FastAPI:
    """Crea una FastAPI con overrides dependientes del usuario actuante."""
    app = FastAPI()
    app.include_router(inbox_router, prefix="/api/v1/inbox")

    async def _get_db_override():
        yield db

    async def _require_staff_override():
        return acting_user

    async def _require_manager_override():
        # require_manager real valida el rol, aqui dejamos pasar a manager+
        if acting_user.role not in ("admin", "superadmin", "manager"):
            from fastapi import HTTPException
            raise HTTPException(403, "Se requieren permisos de gestor")
        return acting_user

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[require_staff] = _require_staff_override
    app.dependency_overrides[require_manager] = _require_manager_override
    return app


@pytest_asyncio.fixture
async def client_mgr(tpl_engine_db, manager_user):
    app = _build_app(tpl_engine_db, manager_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_agent(tpl_engine_db, agent_user):
    app = _build_app(tpl_engine_db, agent_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_other(tpl_engine_db, other_agent):
    app = _build_app(tpl_engine_db, other_agent)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _make_pedido(db, creator: User, ref: str = "P-TEST") -> Pedido:
    p = Pedido(
        reference=ref, title="T",
        description="", state="active",
        created_by=creator.id, currency="BOB",
        client_whatsapp="+591 71234567",
        item_count=0, quotes_received=0,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def _make_session(db, pedido: Pedido, **kwargs) -> ConversationSession:
    s = ConversationSession(pedido_id=pedido.id, state="active", **kwargs)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


# ── 5.3 Notas internas ────────────────────────────────────────
class TestInternalNotes:
    async def test_note_creates_message_with_sender_type_note(
        self, client_agent, tpl_engine_db, manager_user, agent_user
    ):
        p = await _make_pedido(tpl_engine_db, manager_user)
        s = await _make_session(tpl_engine_db, p)

        resp = await client_agent.post(
            f"/api/v1/inbox/sessions/{s.id}/note",
            json={"text": "Recordar llamar al cliente manana"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        d = body["data"]
        assert d["direction"] == "internal"
        assert d["channel"] == "web"
        assert d["sender_type"] == "note"
        assert d["sender_ref"] == str(agent_user.id)
        # Body incluye nombre del autor
        assert "Agent Tester" in d["body"]
        assert "Recordar llamar" in d["body"]

        # Verificar que realmente se guardo en DB
        rows = (await tpl_engine_db.execute(
            select(Message).where(Message.session_id == s.id)
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].sender_type == "note"

    async def test_note_rejects_empty_text(
        self, client_agent, tpl_engine_db, manager_user
    ):
        p = await _make_pedido(tpl_engine_db, manager_user)
        s = await _make_session(tpl_engine_db, p)

        resp = await client_agent.post(
            f"/api/v1/inbox/sessions/{s.id}/note",
            json={"text": ""},
        )
        assert resp.status_code == 422

    async def test_note_404_when_session_not_found(
        self, client_agent, tpl_engine_db
    ):
        resp = await client_agent.post(
            "/api/v1/inbox/sessions/99999/note",
            json={"text": "hola"},
        )
        assert resp.status_code == 404

    async def test_note_does_not_affect_unread_flag(
        self, client_agent, tpl_engine_db, manager_user
    ):
        """Una nota interna no debe contar como respuesta al cliente."""
        now = datetime.now(timezone.utc)
        p = await _make_pedido(tpl_engine_db, manager_user)
        s = await _make_session(
            tpl_engine_db, p,
            last_client_msg_at=now - timedelta(minutes=5),
        )
        # Agregar nota
        resp = await client_agent.post(
            f"/api/v1/inbox/sessions/{s.id}/note",
            json={"text": "nota interna"},
        )
        assert resp.status_code == 200

        # La sesion sigue sin last_operator_msg_at => sigue siendo unread
        await tpl_engine_db.refresh(s)
        assert s.last_operator_msg_at is None


# ── 5.6 Mark-read ─────────────────────────────────────────────
class TestMarkRead:
    async def test_mark_read_sets_operator_last_read_at(
        self, client_agent, tpl_engine_db, manager_user
    ):
        now = datetime.now(timezone.utc)
        p = await _make_pedido(tpl_engine_db, manager_user)
        s = await _make_session(
            tpl_engine_db, p,
            last_client_msg_at=now - timedelta(minutes=2),
        )
        assert s.operator_last_read_at is None

        resp = await client_agent.post(
            f"/api/v1/inbox/sessions/{s.id}/mark-read"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["read_at"] is not None

        await tpl_engine_db.refresh(s)
        assert s.operator_last_read_at is not None

    async def test_mark_read_makes_session_not_unread(
        self, client_agent, tpl_engine_db, manager_user
    ):
        """Tras mark-read el GET /sessions devuelve unread=false."""
        now = datetime.now(timezone.utc)
        p = await _make_pedido(tpl_engine_db, manager_user)
        s = await _make_session(
            tpl_engine_db, p,
            last_client_msg_at=now - timedelta(minutes=5),
        )

        # Antes: unread
        r1 = await client_agent.get("/api/v1/inbox/sessions")
        assert r1.status_code == 200
        data1 = r1.json()
        assert data1["unread_count"] >= 1
        items1 = {i["id"]: i for i in data1["data"]}
        assert items1[s.id]["unread"] is True

        # Mark-read
        r2 = await client_agent.post(f"/api/v1/inbox/sessions/{s.id}/mark-read")
        assert r2.status_code == 200

        # Despues: ya no unread
        r3 = await client_agent.get("/api/v1/inbox/sessions")
        data3 = r3.json()
        items3 = {i["id"]: i for i in data3["data"]}
        assert items3[s.id]["unread"] is False
        assert data3["unread_count"] == 0

    async def test_mark_read_unread_only_filter(
        self, client_agent, tpl_engine_db, manager_user
    ):
        """La sesion marcada como leida debe desaparecer de unread_only=true."""
        now = datetime.now(timezone.utc)
        p1 = await _make_pedido(tpl_engine_db, manager_user, "P-1")
        p2 = await _make_pedido(tpl_engine_db, manager_user, "P-2")
        s1 = await _make_session(
            tpl_engine_db, p1, last_client_msg_at=now - timedelta(minutes=1),
        )
        s2 = await _make_session(
            tpl_engine_db, p2, last_client_msg_at=now - timedelta(minutes=2),
        )

        # Antes: ambas en unread_only
        r = await client_agent.get("/api/v1/inbox/sessions?unread_only=true")
        ids = {i["id"] for i in r.json()["data"]}
        assert s1.id in ids and s2.id in ids

        # Marcar s1 como leida
        await client_agent.post(f"/api/v1/inbox/sessions/{s1.id}/mark-read")

        r2 = await client_agent.get("/api/v1/inbox/sessions?unread_only=true")
        ids2 = {i["id"] for i in r2.json()["data"]}
        assert s1.id not in ids2
        assert s2.id in ids2

    async def test_mark_read_404(self, client_agent):
        resp = await client_agent.post("/api/v1/inbox/sessions/99999/mark-read")
        assert resp.status_code == 404

    async def test_new_client_msg_after_read_makes_unread_again(
        self, client_agent, tpl_engine_db, manager_user
    ):
        """Si el cliente envia algo despues de mark-read => unread otra vez."""
        now = datetime.now(timezone.utc)
        p = await _make_pedido(tpl_engine_db, manager_user)
        s = await _make_session(
            tpl_engine_db, p,
            last_client_msg_at=now - timedelta(minutes=10),
        )
        # mark-read
        await client_agent.post(f"/api/v1/inbox/sessions/{s.id}/mark-read")
        await tpl_engine_db.refresh(s)
        assert s.operator_last_read_at is not None

        # Cliente envia nuevo mensaje DESPUES del read
        s.last_client_msg_at = datetime.now(timezone.utc) + timedelta(seconds=1)
        await tpl_engine_db.commit()

        r = await client_agent.get("/api/v1/inbox/sessions")
        items = {i["id"]: i for i in r.json()["data"]}
        assert items[s.id]["unread"] is True


# ── 5.4 Templates CRUD ────────────────────────────────────────
class TestTemplatesList:
    async def test_list_empty(self, client_agent):
        resp = await client_agent.get("/api/v1/inbox/templates")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "data": []}

    async def test_list_shows_globals_and_own_personal(
        self, client_agent, tpl_engine_db,
        agent_user, other_agent, manager_user,
    ):
        # Global creada por manager
        g = InboxTemplate(title="Saludo", body="Hola", scope="global", owner_id=None)
        # Personal del agente actual
        mine = InboxTemplate(title="Mia", body="mi body", scope="personal", owner_id=agent_user.id)
        # Personal de otro agente (NO debe aparecer)
        theirs = InboxTemplate(title="Otros", body="...", scope="personal", owner_id=other_agent.id)
        tpl_engine_db.add_all([g, mine, theirs])
        await tpl_engine_db.commit()

        resp = await client_agent.get("/api/v1/inbox/templates")
        data = resp.json()["data"]
        titles = {t["title"] for t in data}
        assert "Saludo" in titles
        assert "Mia" in titles
        assert "Otros" not in titles


class TestTemplatesCreate:
    async def test_agent_can_create_personal(
        self, client_agent, tpl_engine_db, agent_user
    ):
        resp = await client_agent.post(
            "/api/v1/inbox/templates",
            json={"title": "Hola", "body": "Buenos dias", "scope": "personal"},
        )
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["scope"] == "personal"
        assert d["owner_id"] == agent_user.id
        assert d["title"] == "Hola"

    async def test_agent_cannot_create_global(self, client_agent):
        resp = await client_agent.post(
            "/api/v1/inbox/templates",
            json={"title": "G", "body": "b", "scope": "global"},
        )
        assert resp.status_code == 403

    async def test_manager_can_create_global(
        self, client_mgr, tpl_engine_db
    ):
        resp = await client_mgr.post(
            "/api/v1/inbox/templates",
            json={"title": "G", "body": "b", "scope": "global"},
        )
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["scope"] == "global"
        assert d["owner_id"] is None

    async def test_create_validates_scope(self, client_agent):
        resp = await client_agent.post(
            "/api/v1/inbox/templates",
            json={"title": "X", "body": "y", "scope": "invalid"},
        )
        assert resp.status_code == 422

    async def test_create_title_required(self, client_agent):
        resp = await client_agent.post(
            "/api/v1/inbox/templates",
            json={"title": "", "body": "y", "scope": "personal"},
        )
        assert resp.status_code == 422


class TestTemplatesUpdate:
    async def test_owner_can_edit_own_personal(
        self, client_agent, tpl_engine_db, agent_user
    ):
        t = InboxTemplate(
            title="Old", body="old body", scope="personal",
            owner_id=agent_user.id,
        )
        tpl_engine_db.add(t)
        await tpl_engine_db.commit()
        await tpl_engine_db.refresh(t)

        resp = await client_agent.put(
            f"/api/v1/inbox/templates/{t.id}",
            json={"title": "New", "body": "new body", "scope": "personal"},
        )
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["title"] == "New"
        assert d["body"] == "new body"

    async def test_agent_cannot_edit_another_personal(
        self, client_agent, tpl_engine_db, other_agent
    ):
        t = InboxTemplate(
            title="Other", body="b", scope="personal",
            owner_id=other_agent.id,
        )
        tpl_engine_db.add(t)
        await tpl_engine_db.commit()
        await tpl_engine_db.refresh(t)

        resp = await client_agent.put(
            f"/api/v1/inbox/templates/{t.id}",
            json={"title": "X", "body": "y", "scope": "personal"},
        )
        assert resp.status_code == 403

    async def test_agent_cannot_edit_global(
        self, client_agent, tpl_engine_db
    ):
        t = InboxTemplate(title="G", body="b", scope="global", owner_id=None)
        tpl_engine_db.add(t)
        await tpl_engine_db.commit()
        await tpl_engine_db.refresh(t)

        resp = await client_agent.put(
            f"/api/v1/inbox/templates/{t.id}",
            json={"title": "X", "body": "y", "scope": "global"},
        )
        assert resp.status_code == 403

    async def test_manager_can_edit_global(
        self, client_mgr, tpl_engine_db
    ):
        t = InboxTemplate(title="G", body="b", scope="global", owner_id=None)
        tpl_engine_db.add(t)
        await tpl_engine_db.commit()
        await tpl_engine_db.refresh(t)

        resp = await client_mgr.put(
            f"/api/v1/inbox/templates/{t.id}",
            json={"title": "G2", "body": "b2", "scope": "global"},
        )
        assert resp.status_code == 200

    async def test_agent_cannot_escalate_personal_to_global(
        self, client_agent, tpl_engine_db, agent_user
    ):
        t = InboxTemplate(
            title="P", body="b", scope="personal",
            owner_id=agent_user.id,
        )
        tpl_engine_db.add(t)
        await tpl_engine_db.commit()
        await tpl_engine_db.refresh(t)

        resp = await client_agent.put(
            f"/api/v1/inbox/templates/{t.id}",
            json={"title": "P", "body": "b", "scope": "global"},
        )
        assert resp.status_code == 403

    async def test_update_404(self, client_agent):
        resp = await client_agent.put(
            "/api/v1/inbox/templates/99999",
            json={"title": "x", "body": "y", "scope": "personal"},
        )
        assert resp.status_code == 404


class TestTemplatesDelete:
    async def test_owner_can_delete_own(
        self, client_agent, tpl_engine_db, agent_user
    ):
        t = InboxTemplate(
            title="P", body="b", scope="personal", owner_id=agent_user.id,
        )
        tpl_engine_db.add(t)
        await tpl_engine_db.commit()
        await tpl_engine_db.refresh(t)

        resp = await client_agent.delete(f"/api/v1/inbox/templates/{t.id}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Realmente borrada
        row = await tpl_engine_db.get(InboxTemplate, t.id)
        assert row is None

    async def test_agent_cannot_delete_global(
        self, client_agent, tpl_engine_db
    ):
        t = InboxTemplate(title="G", body="b", scope="global", owner_id=None)
        tpl_engine_db.add(t)
        await tpl_engine_db.commit()
        await tpl_engine_db.refresh(t)

        resp = await client_agent.delete(f"/api/v1/inbox/templates/{t.id}")
        assert resp.status_code == 403

    async def test_manager_can_delete_global(
        self, client_mgr, tpl_engine_db
    ):
        t = InboxTemplate(title="G", body="b", scope="global", owner_id=None)
        tpl_engine_db.add(t)
        await tpl_engine_db.commit()
        await tpl_engine_db.refresh(t)

        resp = await client_mgr.delete(f"/api/v1/inbox/templates/{t.id}")
        assert resp.status_code == 200

    async def test_delete_404(self, client_agent):
        resp = await client_agent.delete("/api/v1/inbox/templates/99999")
        assert resp.status_code == 404


# ── Auth ──────────────────────────────────────────────────────
class TestAuthRequired:
    async def test_endpoints_require_staff(self, tpl_engine_db):
        """Sin override de require_staff, todos los endpoints rechazan."""
        app = FastAPI()
        app.include_router(inbox_router, prefix="/api/v1/inbox")

        async def _get_db_override():
            yield tpl_engine_db

        app.dependency_overrides[get_db] = _get_db_override

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            for method, url, body in [
                ("POST", "/api/v1/inbox/sessions/1/note", {"text": "x"}),
                ("POST", "/api/v1/inbox/sessions/1/mark-read", None),
                ("GET", "/api/v1/inbox/templates", None),
                ("POST", "/api/v1/inbox/templates",
                 {"title": "t", "body": "b", "scope": "personal"}),
            ]:
                if method == "GET":
                    r = await c.get(url)
                elif body is None:
                    r = await c.post(url)
                else:
                    r = await c.post(url, json=body)
                assert r.status_code in (401, 403), f"{method} {url} => {r.status_code}"
