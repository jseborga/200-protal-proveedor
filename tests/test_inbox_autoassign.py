"""Tests de auto-asignacion round-robin / least-loaded (Fase 5.7).

Cubre:
- get_config / save_config (defaults + upsert + normalizacion).
- _pick_round_robin (wrap around, primer pick, pool vacio).
- _pick_least_loaded (desempate estable, filtro closed, pool vacio).
- auto_assign_if_needed (disabled, ya asignado, sin eligibles, exito + Message).
- Endpoints /admin/inbox-autoassign (GET/PUT + RBAC + validacion pool).
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, Integer, select

from app.api.deps import require_manager
from app.api.routes.admin import router as admin_router
from app.core.database import get_db
from app.models.conversation import ConversationSession, Message
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services.inbox_autoassign import (
    _pick_round_robin,
    _pick_least_loaded,
    auto_assign_if_needed,
    get_config,
    save_config,
)


@pytest_asyncio.fixture
async def aa_db(db):
    """Crea mkt_system_setting en el engine SQLite (JSONB -> JSON)."""
    SystemSetting.__table__.c.value.type = JSON()
    eng = db.bind
    async with eng.begin() as conn:
        await conn.run_sync(
            lambda sc: SystemSetting.__table__.create(sc, checkfirst=True)
        )
    return db


@pytest_asyncio.fixture
async def manager_user(aa_db) -> User:
    u = User(
        email="mgr@test.com",
        hashed_password="x",
        full_name="Manager",
        role="manager",
        is_active=True,
    )
    aa_db.add(u)
    await aa_db.commit()
    await aa_db.refresh(u)
    return u


@pytest_asyncio.fixture
async def agents_pool(aa_db) -> list[User]:
    """Tres field_agent activos para las pruebas de round-robin / load."""
    users = []
    for i, name in enumerate(["Agente A", "Agente B", "Agente C"]):
        u = User(
            email=f"a{i}@test.com",
            hashed_password="x",
            full_name=name,
            role="field_agent",
            is_active=True,
        )
        aa_db.add(u)
        users.append(u)
    await aa_db.commit()
    for u in users:
        await aa_db.refresh(u)
    return users


# ──────────────────────────────────────────────────────────────────
# Unidad: get_config / save_config
# ──────────────────────────────────────────────────────────────────
class TestConfig:
    async def test_get_returns_defaults_when_empty(self, aa_db):
        cfg = await get_config(aa_db)
        assert cfg["enabled"] is False
        assert cfg["strategy"] == "round_robin"
        assert cfg["pool_user_ids"] == []
        assert cfg["last_assigned_user_id"] is None

    async def test_save_and_read_back(self, aa_db):
        saved = await save_config(aa_db, {
            "enabled": True,
            "strategy": "least_loaded",
            "pool_user_ids": [1, 2, 3],
            "last_assigned_user_id": 2,
        })
        assert saved["enabled"] is True
        assert saved["strategy"] == "least_loaded"
        assert saved["pool_user_ids"] == [1, 2, 3]

        # persistido
        cfg2 = await get_config(aa_db)
        assert cfg2["enabled"] is True
        assert cfg2["last_assigned_user_id"] == 2

    async def test_save_normalizes_invalid_strategy(self, aa_db):
        saved = await save_config(aa_db, {
            "enabled": True,
            "strategy": "totally_invalid",
        })
        # strategy cae al default
        assert saved["strategy"] == "round_robin"

    async def test_save_upsert(self, aa_db):
        await save_config(aa_db, {"enabled": True})
        await save_config(aa_db, {"enabled": False, "strategy": "least_loaded"})
        cfg = await get_config(aa_db)
        assert cfg["enabled"] is False
        assert cfg["strategy"] == "least_loaded"


# ──────────────────────────────────────────────────────────────────
# Unidad: _pick_round_robin
# ──────────────────────────────────────────────────────────────────
class TestRoundRobin:
    async def test_empty_returns_none(self):
        assert _pick_round_robin([], None) is None

    async def test_no_cursor_picks_first(self, agents_pool):
        picked = _pick_round_robin(agents_pool, None)
        assert picked.id == agents_pool[0].id

    async def test_cursor_picks_next(self, agents_pool):
        picked = _pick_round_robin(agents_pool, agents_pool[0].id)
        assert picked.id == agents_pool[1].id

    async def test_wrap_around(self, agents_pool):
        picked = _pick_round_robin(agents_pool, agents_pool[-1].id)
        assert picked.id == agents_pool[0].id

    async def test_cursor_beyond_all(self, agents_pool):
        # Cursor con id muy alto -> wrap al primero
        picked = _pick_round_robin(agents_pool, 999999)
        assert picked.id == agents_pool[0].id


# ──────────────────────────────────────────────────────────────────
# Unidad: _pick_least_loaded
# ──────────────────────────────────────────────────────────────────
class TestLeastLoaded:
    async def test_empty_returns_none(self, aa_db):
        assert await _pick_least_loaded(aa_db, []) is None

    async def test_picks_operator_with_fewest_open(self, aa_db, agents_pool, sample_pedido):
        # A: 2 abiertas, B: 0, C: 1 -> espera B
        a, b, c = agents_pool
        sessions = [
            ConversationSession(pedido_id=sample_pedido.id, client_phone="1",
                                state="active", operator_id=a.id),
            ConversationSession(pedido_id=sample_pedido.id, client_phone="2",
                                state="active", operator_id=a.id),
            ConversationSession(pedido_id=sample_pedido.id, client_phone="3",
                                state="active", operator_id=c.id),
            ConversationSession(pedido_id=sample_pedido.id, client_phone="4",
                                state="closed", operator_id=b.id),  # cerrada no cuenta
        ]
        for s in sessions:
            aa_db.add(s)
        await aa_db.commit()

        picked = await _pick_least_loaded(aa_db, agents_pool)
        assert picked.id == b.id

    async def test_tiebreak_by_id_asc(self, aa_db, agents_pool):
        # Todos en 0 -> debe elegir el de id menor (primer en orden)
        picked = await _pick_least_loaded(aa_db, agents_pool)
        assert picked.id == agents_pool[0].id


# ──────────────────────────────────────────────────────────────────
# Unidad: auto_assign_if_needed
# ──────────────────────────────────────────────────────────────────
class TestAutoAssignIfNeeded:
    async def test_noop_when_disabled(self, aa_db, agents_pool, sample_session):
        # enabled por default = False
        result = await auto_assign_if_needed(aa_db, sample_session)
        assert result is None
        assert sample_session.operator_id is None

    async def test_noop_when_already_assigned(self, aa_db, agents_pool, sample_session):
        await save_config(aa_db, {"enabled": True, "strategy": "round_robin"})
        sample_session.operator_id = agents_pool[0].id
        await aa_db.commit()
        result = await auto_assign_if_needed(aa_db, sample_session)
        assert result is None

    async def test_noop_when_no_eligible(self, aa_db, sample_session):
        await save_config(aa_db, {"enabled": True, "strategy": "round_robin"})
        result = await auto_assign_if_needed(aa_db, sample_session)
        assert result is None

    async def test_assigns_and_inserts_system_message(
        self, aa_db, agents_pool, sample_session
    ):
        await save_config(aa_db, {"enabled": True, "strategy": "round_robin"})
        picked = await auto_assign_if_needed(aa_db, sample_session)
        assert picked is not None
        assert picked.id == agents_pool[0].id
        assert sample_session.operator_id == picked.id

        # Mensaje de sistema creado
        msgs = (await aa_db.execute(
            select(Message).where(Message.session_id == sample_session.id)
        )).scalars().all()
        sys_msgs = [m for m in msgs if m.sender_type == "system"]
        assert len(sys_msgs) == 1
        assert "Auto-asignado" in (sys_msgs[0].body or "")
        assert sys_msgs[0].direction == "internal"
        assert sys_msgs[0].channel == "web"

    async def test_round_robin_advances_cursor(
        self, aa_db, agents_pool, sample_pedido
    ):
        await save_config(aa_db, {"enabled": True, "strategy": "round_robin"})

        # Sesion 1 -> agente 0
        s1 = ConversationSession(pedido_id=sample_pedido.id, client_phone="1", state="active")
        aa_db.add(s1)
        await aa_db.commit()
        await aa_db.refresh(s1)
        p1 = await auto_assign_if_needed(aa_db, s1)

        # Sesion 2 -> agente 1
        s2 = ConversationSession(pedido_id=sample_pedido.id, client_phone="2", state="active")
        aa_db.add(s2)
        await aa_db.commit()
        await aa_db.refresh(s2)
        p2 = await auto_assign_if_needed(aa_db, s2)

        assert p1.id == agents_pool[0].id
        assert p2.id == agents_pool[1].id

    async def test_pool_filter(self, aa_db, agents_pool, sample_session):
        # Solo incluir al agente C (id mas alto) en el pool
        c = agents_pool[-1]
        await save_config(aa_db, {
            "enabled": True, "strategy": "round_robin", "pool_user_ids": [c.id],
        })
        picked = await auto_assign_if_needed(aa_db, sample_session)
        assert picked.id == c.id


# ──────────────────────────────────────────────────────────────────
# Integracion: endpoints /admin/inbox-autoassign
# ──────────────────────────────────────────────────────────────────
def _build_admin_app(db, acting_user: User) -> FastAPI:
    app = FastAPI()
    app.include_router(admin_router, prefix="/api/v1/admin")

    async def _get_db_override():
        yield db

    async def _require_manager_override():
        return acting_user

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[require_manager] = _require_manager_override
    return app


@pytest_asyncio.fixture
async def manager_client(aa_db, manager_user):
    app = _build_admin_app(aa_db, manager_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


class TestEndpoints:
    async def test_get_returns_defaults(self, manager_client, agents_pool):
        resp = await manager_client.get("/api/v1/admin/inbox-autoassign")
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["enabled"] is False
        assert "operators" in d
        assert len(d["operators"]) >= 3  # 3 agents_pool
        # strategies expuesto para UI
        assert set(d["strategies"]) == {"round_robin", "least_loaded"}

    async def test_put_saves_config(self, manager_client, agents_pool):
        a, b, _ = agents_pool
        resp = await manager_client.put(
            "/api/v1/admin/inbox-autoassign",
            json={"enabled": True, "strategy": "least_loaded", "pool_user_ids": [a.id, b.id]},
        )
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["enabled"] is True
        assert d["strategy"] == "least_loaded"
        assert sorted(d["pool_user_ids"]) == sorted([a.id, b.id])

    async def test_put_rejects_non_staff_user_ids(
        self, manager_client, agents_pool, aa_db
    ):
        # Crear un user no-staff
        u = User(email="buyer@test.com", hashed_password="x", full_name="Buyer",
                 role="user", is_active=True)
        aa_db.add(u)
        await aa_db.commit()
        await aa_db.refresh(u)

        resp = await manager_client.put(
            "/api/v1/admin/inbox-autoassign",
            json={"enabled": True, "strategy": "round_robin", "pool_user_ids": [u.id]},
        )
        assert resp.status_code == 400

    async def test_put_rejects_invalid_strategy(self, manager_client):
        resp = await manager_client.put(
            "/api/v1/admin/inbox-autoassign",
            json={"enabled": True, "strategy": "bogus", "pool_user_ids": []},
        )
        # Pydantic Literal -> 422
        assert resp.status_code == 422
