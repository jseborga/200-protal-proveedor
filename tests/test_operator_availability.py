"""Tests del service operator_availability (Fase 5.8).

Cubre:
- is_on_duty puro: schedule vacio, dentro/fuera, bordes, multi-ventana.
- get_schedule_by_user: sin user_ids, con usuarios sin filas.
- filter_on_duty: preserva orden, mezcla con/sin schedule.
- save_schedule: upsert (reemplaza), validaciones weekday/time.
- Endpoints /admin/operator-schedule/{user_id}: GET/PUT + RBAC + 404.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import require_manager
from app.api.routes.admin import router as admin_router
from app.core.database import get_db
from app.models.operator_schedule import OperatorSchedule
from app.models.user import User
from app.services.operator_availability import (
    filter_on_duty,
    get_schedule_by_user,
    is_on_duty,
    list_schedule,
    save_schedule,
)


@pytest_asyncio.fixture
async def os_db(db):
    """Crea mkt_operator_schedule en el engine SQLite."""
    eng = db.bind
    async with eng.begin() as conn:
        await conn.run_sync(
            lambda sc: OperatorSchedule.__table__.create(sc, checkfirst=True)
        )
    return db


@pytest_asyncio.fixture
async def manager_user(os_db) -> User:
    u = User(
        email="mgr@test.com",
        hashed_password="x",
        full_name="Manager",
        role="manager",
        is_active=True,
    )
    os_db.add(u)
    await os_db.commit()
    await os_db.refresh(u)
    return u


@pytest_asyncio.fixture
async def agents_pool(os_db) -> list[User]:
    users = []
    for i, name in enumerate(["Agente A", "Agente B", "Agente C"]):
        u = User(
            email=f"agent{i}@test.com",
            hashed_password="x",
            full_name=name,
            role="field_agent",
            is_active=True,
        )
        os_db.add(u)
        users.append(u)
    await os_db.commit()
    for u in users:
        await os_db.refresh(u)
    return users


# ──────────────────────────────────────────────────────────────────
# Unidad: is_on_duty
# ──────────────────────────────────────────────────────────────────
class TestIsOnDuty:
    def test_empty_schedule_always_on_duty(self):
        # Sin rows = backward compat = on-duty
        now = datetime(2026, 4, 22, 10, 0)  # wed 10am
        assert is_on_duty(None, now) is True
        assert is_on_duty([], now) is True

    def test_inside_window(self):
        # weekday=2 (miercoles) 09-17, now=miercoles 10am
        now = datetime(2026, 4, 22, 10, 0)  # weekday()=2
        assert now.weekday() == 2
        schedule = [(2, time(9, 0), time(17, 0))]
        assert is_on_duty(schedule, now) is True

    def test_outside_window_same_day(self):
        now = datetime(2026, 4, 22, 18, 0)  # wed 18:00, fuera de 09-17
        schedule = [(2, time(9, 0), time(17, 0))]
        assert is_on_duty(schedule, now) is False

    def test_wrong_weekday(self):
        # schedule lunes 09-17, now=miercoles 10am
        now = datetime(2026, 4, 22, 10, 0)  # wed
        schedule = [(0, time(9, 0), time(17, 0))]  # mon
        assert is_on_duty(schedule, now) is False

    def test_start_inclusive_end_exclusive(self):
        schedule = [(2, time(9, 0), time(17, 0))]
        # start exacto: inclusive
        now_start = datetime(2026, 4, 22, 9, 0)
        assert is_on_duty(schedule, now_start) is True
        # end exacto: exclusive
        now_end = datetime(2026, 4, 22, 17, 0)
        assert is_on_duty(schedule, now_end) is False

    def test_multi_window_same_day(self):
        # 09-13 y 15-18 miercoles
        schedule = [
            (2, time(9, 0), time(13, 0)),
            (2, time(15, 0), time(18, 0)),
        ]
        # entre ventanas: off
        gap = datetime(2026, 4, 22, 14, 0)
        assert is_on_duty(schedule, gap) is False
        # dentro de primera
        w1 = datetime(2026, 4, 22, 12, 0)
        assert is_on_duty(schedule, w1) is True
        # dentro de segunda
        w2 = datetime(2026, 4, 22, 16, 0)
        assert is_on_duty(schedule, w2) is True


# ──────────────────────────────────────────────────────────────────
# Unidad: get_schedule_by_user
# ──────────────────────────────────────────────────────────────────
class TestGetScheduleByUser:
    async def test_empty_ids_returns_empty(self, os_db):
        result = await get_schedule_by_user(os_db, [])
        assert result == {}

    async def test_users_without_rows_absent(self, os_db, agents_pool):
        # Ningun operador tiene schedule -> dict vacio
        result = await get_schedule_by_user(os_db, [u.id for u in agents_pool])
        assert result == {}

    async def test_returns_windows_per_user(self, os_db, agents_pool):
        a = agents_pool[0]
        os_db.add(OperatorSchedule(
            user_id=a.id, weekday=2, start_time=time(9, 0), end_time=time(17, 0),
        ))
        os_db.add(OperatorSchedule(
            user_id=a.id, weekday=3, start_time=time(10, 0), end_time=time(18, 0),
        ))
        await os_db.commit()
        result = await get_schedule_by_user(os_db, [a.id])
        assert a.id in result
        assert len(result[a.id]) == 2


# ──────────────────────────────────────────────────────────────────
# Unidad: filter_on_duty
# ──────────────────────────────────────────────────────────────────
class TestFilterOnDuty:
    async def test_no_schedule_passes_all(self, os_db, agents_pool):
        now = datetime(2026, 4, 22, 10, 0, tzinfo=ZoneInfo("America/La_Paz"))
        result = await filter_on_duty(os_db, agents_pool, now=now)
        assert [u.id for u in result] == [u.id for u in agents_pool]

    async def test_preserves_order(self, os_db, agents_pool):
        # A sin schedule, B con schedule fuera, C sin schedule
        b = agents_pool[1]
        os_db.add(OperatorSchedule(
            user_id=b.id, weekday=0, start_time=time(9, 0), end_time=time(10, 0),
        ))
        await os_db.commit()
        # miercoles 10am La Paz -> B off-duty (solo tiene lunes 9-10)
        now = datetime(2026, 4, 22, 10, 0, tzinfo=ZoneInfo("America/La_Paz"))
        result = await filter_on_duty(os_db, agents_pool, now=now)
        ids = [u.id for u in result]
        assert agents_pool[0].id in ids
        assert agents_pool[1].id not in ids
        assert agents_pool[2].id in ids
        # orden preservado
        assert ids == [agents_pool[0].id, agents_pool[2].id]

    async def test_empty_input(self, os_db):
        assert await filter_on_duty(os_db, []) == []


# ──────────────────────────────────────────────────────────────────
# Unidad: save_schedule / list_schedule
# ──────────────────────────────────────────────────────────────────
class TestSaveSchedule:
    async def test_saves_and_reads_back(self, os_db, agents_pool):
        a = agents_pool[0]
        saved = await save_schedule(os_db, a.id, [
            {"weekday": 0, "start_time": "09:00", "end_time": "13:00"},
            {"weekday": 0, "start_time": "15:00", "end_time": "18:00"},
            {"weekday": 4, "start_time": "09:00", "end_time": "17:00"},
        ])
        assert len(saved) == 3
        read = await list_schedule(os_db, a.id)
        assert len(read) == 3

    async def test_replaces_existing(self, os_db, agents_pool):
        a = agents_pool[0]
        await save_schedule(os_db, a.id, [
            {"weekday": 0, "start_time": "09:00", "end_time": "17:00"},
        ])
        await save_schedule(os_db, a.id, [
            {"weekday": 1, "start_time": "10:00", "end_time": "14:00"},
        ])
        read = await list_schedule(os_db, a.id)
        assert len(read) == 1
        assert read[0]["weekday"] == 1

    async def test_empty_clears(self, os_db, agents_pool):
        a = agents_pool[0]
        await save_schedule(os_db, a.id, [
            {"weekday": 0, "start_time": "09:00", "end_time": "17:00"},
        ])
        await save_schedule(os_db, a.id, [])
        read = await list_schedule(os_db, a.id)
        assert read == []

    async def test_rejects_bad_weekday(self, os_db, agents_pool):
        a = agents_pool[0]
        with pytest.raises(ValueError, match="weekday"):
            await save_schedule(os_db, a.id, [
                {"weekday": 7, "start_time": "09:00", "end_time": "17:00"},
            ])

    async def test_rejects_start_ge_end(self, os_db, agents_pool):
        a = agents_pool[0]
        with pytest.raises(ValueError, match="start_time debe ser"):
            await save_schedule(os_db, a.id, [
                {"weekday": 0, "start_time": "17:00", "end_time": "09:00"},
            ])

    async def test_rejects_invalid_time_format(self, os_db, agents_pool):
        a = agents_pool[0]
        with pytest.raises(ValueError):
            await save_schedule(os_db, a.id, [
                {"weekday": 0, "start_time": "25:99", "end_time": "17:00"},
            ])


# ──────────────────────────────────────────────────────────────────
# Integracion: endpoints /admin/operator-schedule/{user_id}
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
async def manager_client(os_db, manager_user):
    app = _build_admin_app(os_db, manager_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


class TestEndpoints:
    async def test_get_empty_schedule(self, manager_client, agents_pool):
        a = agents_pool[0]
        resp = await manager_client.get(f"/api/v1/admin/operator-schedule/{a.id}")
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["user_id"] == a.id
        assert d["windows"] == []

    async def test_put_saves_windows(self, manager_client, agents_pool):
        a = agents_pool[0]
        resp = await manager_client.put(
            f"/api/v1/admin/operator-schedule/{a.id}",
            json={"windows": [
                {"weekday": 0, "start_time": "09:00", "end_time": "13:00"},
                {"weekday": 4, "start_time": "10:00", "end_time": "18:00"},
            ]},
        )
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert len(d["windows"]) == 2

    async def test_put_rejects_invalid_weekday(self, manager_client, agents_pool):
        a = agents_pool[0]
        resp = await manager_client.put(
            f"/api/v1/admin/operator-schedule/{a.id}",
            json={"windows": [
                {"weekday": 9, "start_time": "09:00", "end_time": "13:00"},
            ]},
        )
        # Pydantic Field(ge=0, le=6) -> 422
        assert resp.status_code == 422

    async def test_put_rejects_bad_time_range(self, manager_client, agents_pool):
        a = agents_pool[0]
        resp = await manager_client.put(
            f"/api/v1/admin/operator-schedule/{a.id}",
            json={"windows": [
                {"weekday": 0, "start_time": "17:00", "end_time": "09:00"},
            ]},
        )
        # Service valida y lanza ValueError -> HTTPException 400
        assert resp.status_code == 400

    async def test_get_404_for_unknown_user(self, manager_client):
        resp = await manager_client.get("/api/v1/admin/operator-schedule/99999")
        assert resp.status_code == 404

    async def test_put_400_for_non_staff_user(self, manager_client, os_db):
        # Usuario no-staff
        u = User(
            email="buyer@test.com", hashed_password="x", full_name="Buyer",
            role="user", is_active=True,
        )
        os_db.add(u)
        await os_db.commit()
        await os_db.refresh(u)
        resp = await manager_client.put(
            f"/api/v1/admin/operator-schedule/{u.id}",
            json={"windows": []},
        )
        assert resp.status_code == 400
