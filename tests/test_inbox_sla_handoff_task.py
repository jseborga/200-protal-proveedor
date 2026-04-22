"""Tests Fase 5.10: tarea programada inbox_sla_handoff.

Cubre:
- Respetar flag enabled.
- Procesar sesiones breached y reportar stats.
- Filtrar sesiones segun criterio SLA.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from sqlalchemy import JSON

from app.models.conversation import ConversationSession
from app.models.operator_schedule import OperatorSchedule
from app.models.pedido import Pedido
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services.inbox_autoassign import save_config as save_aa_config
from app.services.inbox_sla_handoff import save_handoff_config
from app.tasks import inbox_sla_handoff as handoff_task


@pytest_asyncio.fixture
async def task_db(db):
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


@pytest_asyncio.fixture(autouse=True)
async def _no_push():
    with patch(
        "app.services.webpush.send_push_to_user",
        new=AsyncMock(return_value=0),
    ):
        yield


@pytest_asyncio.fixture
async def two_ops(task_db):
    a = User(email="ta@h.com", hashed_password="x", full_name="T A",
             role="field_agent", is_active=True)
    b = User(email="tb@h.com", hashed_password="x", full_name="T B",
             role="field_agent", is_active=True)
    task_db.add_all([a, b])
    await task_db.commit()
    await task_db.refresh(a)
    await task_db.refresh(b)
    return a, b


async def _make_session(db, *, operator_id, last_client_hours_ago):
    """Crea un Pedido y ConversationSession con last_client_msg_at en el pasado."""
    ped = Pedido(
        reference=f"PED-{operator_id}-{last_client_hours_ago}",
        title="t", description="d", state="active",
        created_by=operator_id, currency="BOB",
        client_whatsapp="+591 71000000", item_count=0, quotes_received=0,
    )
    db.add(ped)
    await db.commit()
    await db.refresh(ped)
    sess = ConversationSession(
        pedido_id=ped.id,
        client_phone="59171000000",
        state="active",
        operator_id=operator_id,
        last_client_msg_at=datetime.now(timezone.utc) - timedelta(hours=last_client_hours_ago),
    )
    db.add(sess)
    await db.commit()
    await db.refresh(sess)
    return sess


class TestRunDisabled:
    async def test_returns_skipped_when_disabled(self, task_db, two_ops):
        a, _ = two_ops
        sess = await _make_session(task_db, operator_id=a.id, last_client_hours_ago=5)
        # enabled=False (default)
        result = await handoff_task.run(task_db)
        assert result["skipped"] == "disabled"
        assert result["checked"] == 0
        assert result["handoffs"] == 0
        # Sesion no fue modificada
        await task_db.refresh(sess)
        assert sess.operator_id == a.id
        assert sess.last_handoff_at is None


class TestRunEnabled:
    async def test_reassigns_breached(self, task_db, two_ops):
        a, b = two_ops
        await save_handoff_config(task_db, {"enabled": True, "threshold_hours": 4})
        await save_aa_config(task_db, {
            "enabled": True, "strategy": "round_robin",
            "pool_user_ids": [a.id, b.id],
        })
        sess = await _make_session(task_db, operator_id=a.id, last_client_hours_ago=5)
        result = await handoff_task.run(task_db)
        assert result["checked"] == 1
        assert result["handoffs"] == 1
        assert result["released"] == 0
        await task_db.refresh(sess)
        assert sess.operator_id == b.id

    async def test_releases_when_no_candidate(self, task_db, two_ops):
        a, _b = two_ops
        await save_handoff_config(task_db, {"enabled": True, "threshold_hours": 4})
        await save_aa_config(task_db, {
            "enabled": True, "strategy": "round_robin",
            "pool_user_ids": [a.id],
        })
        sess = await _make_session(task_db, operator_id=a.id, last_client_hours_ago=5)
        result = await handoff_task.run(task_db)
        assert result["checked"] == 1
        assert result["handoffs"] == 0
        assert result["released"] == 1
        await task_db.refresh(sess)
        assert sess.operator_id is None

    async def test_skips_non_breached(self, task_db, two_ops):
        """Sesion con last_client_msg_at reciente (< threshold) no procesada."""
        a, b = two_ops
        await save_handoff_config(task_db, {"enabled": True, "threshold_hours": 4})
        await save_aa_config(task_db, {
            "enabled": True, "strategy": "round_robin",
            "pool_user_ids": [a.id, b.id],
        })
        sess = await _make_session(task_db, operator_id=a.id, last_client_hours_ago=1)
        result = await handoff_task.run(task_db)
        assert result["checked"] == 0
        assert result["handoffs"] == 0
        await task_db.refresh(sess)
        assert sess.operator_id == a.id

    async def test_reports_threshold_hours(self, task_db, two_ops):
        await save_handoff_config(task_db, {"enabled": True, "threshold_hours": 6})
        result = await handoff_task.run(task_db)
        assert result["threshold_hours"] == 6
