"""Tests de integracion Fase 5.7 + 5.8: auto-asignacion filtrada por horario.

Verifica que `_get_eligible_operators` aplica el filtro on-duty y que
`auto_assign_if_needed`:
- asigna solo operadores on-duty en ese momento,
- respeta operadores sin schedule (backward compat, siempre elegibles),
- deja la sesion sin asignar cuando nadie esta on-duty,
- asigna al unico operador on-duty cuando otros estan off.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from datetime import datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest_asyncio
from sqlalchemy import JSON, select

from app.models.conversation import ConversationSession, Message
from app.models.operator_schedule import OperatorSchedule
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services.inbox_autoassign import auto_assign_if_needed, save_config


@pytest_asyncio.fixture
async def sched_db(db):
    """Crea mkt_system_setting + mkt_operator_schedule en SQLite test engine."""
    SystemSetting.__table__.c.value.type = JSON()
    eng = db.bind
    async with eng.begin() as conn:
        await conn.run_sync(
            lambda sc: SystemSetting.__table__.create(sc, checkfirst=True)
        )
        await conn.run_sync(
            lambda sc: OperatorSchedule.__table__.create(sc, checkfirst=True)
        )
    return db


@pytest_asyncio.fixture
async def agents_ab(sched_db) -> tuple[User, User]:
    a = User(
        email="a@test.com", hashed_password="x", full_name="Agente A",
        role="field_agent", is_active=True,
    )
    b = User(
        email="b@test.com", hashed_password="x", full_name="Agente B",
        role="field_agent", is_active=True,
    )
    sched_db.add_all([a, b])
    await sched_db.commit()
    await sched_db.refresh(a)
    await sched_db.refresh(b)
    return a, b


def _wed_10am():
    """Miercoles 10:00 en La Paz (weekday=2)."""
    return datetime(2026, 4, 22, 10, 0, tzinfo=ZoneInfo("America/La_Paz"))


def _wed_20pm():
    """Miercoles 20:00 en La Paz (weekday=2, fuera de 09-17)."""
    return datetime(2026, 4, 22, 20, 0, tzinfo=ZoneInfo("America/La_Paz"))


class TestAutoAssignWithSchedule:
    async def test_no_schedule_always_assigns(
        self, sched_db, agents_ab, sample_session
    ):
        """Operadores sin schedule definido siguen siendo elegibles."""
        a, b = agents_ab
        await save_config(sched_db, {"enabled": True, "strategy": "round_robin"})
        with patch(
            "app.services.operator_availability.now_local",
            return_value=_wed_20pm(),
        ):
            picked = await auto_assign_if_needed(sched_db, sample_session)
        assert picked is not None
        assert sample_session.operator_id == picked.id

    async def test_respects_on_duty_window(
        self, sched_db, agents_ab, sample_session
    ):
        """A con schedule 09-17 miercoles; mock ahora=10am -> asigna A."""
        a, _b = agents_ab
        # Solo A en el pool, solo A con schedule dentro de rango
        sched_db.add(OperatorSchedule(
            user_id=a.id, weekday=2,
            start_time=time(9, 0), end_time=time(17, 0),
        ))
        await sched_db.commit()
        await save_config(sched_db, {
            "enabled": True, "strategy": "round_robin",
            "pool_user_ids": [a.id],
        })
        with patch(
            "app.services.operator_availability.now_local",
            return_value=_wed_10am(),
        ):
            picked = await auto_assign_if_needed(sched_db, sample_session)
        assert picked is not None
        assert picked.id == a.id

    async def test_off_duty_not_assigned(
        self, sched_db, agents_ab, sample_session
    ):
        """A con schedule 09-17 miercoles; mock ahora=20pm -> no asigna."""
        a, _b = agents_ab
        sched_db.add(OperatorSchedule(
            user_id=a.id, weekday=2,
            start_time=time(9, 0), end_time=time(17, 0),
        ))
        await sched_db.commit()
        await save_config(sched_db, {
            "enabled": True, "strategy": "round_robin",
            "pool_user_ids": [a.id],
        })
        with patch(
            "app.services.operator_availability.now_local",
            return_value=_wed_20pm(),
        ):
            picked = await auto_assign_if_needed(sched_db, sample_session)
        assert picked is None
        assert sample_session.operator_id is None

    async def test_picks_only_on_duty_operator(
        self, sched_db, agents_ab, sample_session
    ):
        """A sin schedule (siempre on-duty), B con 08-12 miercoles.
        A las 14:00 miercoles: B off-duty, pero A sigue elegible -> asigna A.
        """
        a, b = agents_ab
        sched_db.add(OperatorSchedule(
            user_id=b.id, weekday=2,
            start_time=time(8, 0), end_time=time(12, 0),
        ))
        await sched_db.commit()
        await save_config(sched_db, {
            "enabled": True, "strategy": "round_robin",
            "pool_user_ids": [a.id, b.id],
        })
        now_14pm = datetime(2026, 4, 22, 14, 0, tzinfo=ZoneInfo("America/La_Paz"))
        with patch(
            "app.services.operator_availability.now_local",
            return_value=now_14pm,
        ):
            picked = await auto_assign_if_needed(sched_db, sample_session)
        assert picked is not None
        assert picked.id == a.id

    async def test_all_off_duty_no_assignment(
        self, sched_db, agents_ab, sample_session
    ):
        """Ambos operadores con schedules fuera del ahora -> no asigna, no
        crea system message."""
        a, b = agents_ab
        # A solo lunes, B solo martes. Ahora = miercoles.
        sched_db.add(OperatorSchedule(
            user_id=a.id, weekday=0,
            start_time=time(9, 0), end_time=time(17, 0),
        ))
        sched_db.add(OperatorSchedule(
            user_id=b.id, weekday=1,
            start_time=time(9, 0), end_time=time(17, 0),
        ))
        await sched_db.commit()
        await save_config(sched_db, {
            "enabled": True, "strategy": "round_robin",
            "pool_user_ids": [a.id, b.id],
        })
        with patch(
            "app.services.operator_availability.now_local",
            return_value=_wed_10am(),
        ):
            picked = await auto_assign_if_needed(sched_db, sample_session)
        assert picked is None
        assert sample_session.operator_id is None
        # No se crea mensaje de sistema
        msgs = (await sched_db.execute(
            select(Message).where(
                Message.session_id == sample_session.id,
                Message.sender_type == "system",
            )
        )).scalars().all()
        assert len(msgs) == 0
