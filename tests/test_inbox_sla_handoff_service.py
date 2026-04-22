"""Tests Fase 5.10: servicio inbox_sla_handoff.

Cubre:
- Config defaults + normalize/clamping.
- handoff_session: reassigned / released / noop.
- find_breached_sessions: criterio SLA + cooldown + sin operador.
- Integracion con operador on-duty (Fase 5.8).
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest_asyncio
from sqlalchemy import JSON, select

from app.models.conversation import ConversationSession, Message
from app.models.operator_schedule import OperatorSchedule
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services.inbox_autoassign import save_config as save_aa_config
from app.services.inbox_sla_handoff import (
    DEFAULT_CONFIG,
    MAX_THRESHOLD_HOURS,
    MIN_THRESHOLD_HOURS,
    find_breached_sessions,
    get_handoff_config,
    handoff_session,
    save_handoff_config,
)


@pytest_asyncio.fixture
async def ho_db(db):
    """Crea mkt_system_setting + mkt_operator_schedule en SQLite."""
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
async def agents_ab(ho_db):
    a = User(email="a@h.com", hashed_password="x", full_name="Op A",
             role="field_agent", is_active=True)
    b = User(email="b@h.com", hashed_password="x", full_name="Op B",
             role="field_agent", is_active=True)
    ho_db.add_all([a, b])
    await ho_db.commit()
    await ho_db.refresh(a)
    await ho_db.refresh(b)
    return a, b


def _wed_14pm():
    return datetime(2026, 4, 22, 14, 0, tzinfo=ZoneInfo("America/La_Paz"))


# Disable push globally for these tests
@pytest_asyncio.fixture(autouse=True)
async def _no_push():
    with patch(
        "app.services.webpush.send_push_to_user",
        new=AsyncMock(return_value=0),
    ):
        yield


class TestConfig:
    async def test_defaults_when_empty(self, ho_db):
        cfg = await get_handoff_config(ho_db)
        assert cfg == DEFAULT_CONFIG
        assert cfg["enabled"] is False
        assert cfg["threshold_hours"] == 4

    async def test_save_and_roundtrip(self, ho_db):
        saved = await save_handoff_config(ho_db, {"enabled": True, "threshold_hours": 2})
        assert saved["enabled"] is True
        assert saved["threshold_hours"] == 2
        got = await get_handoff_config(ho_db)
        assert got == saved

    async def test_threshold_clamps_too_low(self, ho_db):
        saved = await save_handoff_config(ho_db, {"enabled": True, "threshold_hours": 0})
        assert saved["threshold_hours"] == MIN_THRESHOLD_HOURS

    async def test_threshold_clamps_too_high(self, ho_db):
        saved = await save_handoff_config(ho_db, {"enabled": True, "threshold_hours": 9999})
        assert saved["threshold_hours"] == MAX_THRESHOLD_HOURS

    async def test_threshold_invalid_falls_back_default(self, ho_db):
        saved = await save_handoff_config(ho_db, {"enabled": True, "threshold_hours": "abc"})
        assert saved["threshold_hours"] == DEFAULT_CONFIG["threshold_hours"]


class TestFindBreachedSessions:
    async def test_session_without_operator_not_found(self, ho_db, sample_session):
        now = datetime.now(timezone.utc)
        sample_session.last_client_msg_at = now - timedelta(hours=5)
        await ho_db.commit()
        rows = await find_breached_sessions(ho_db, now, 4)
        assert rows == []

    async def test_operator_read_not_found(self, ho_db, agents_ab, sample_session):
        a, _ = agents_ab
        now = datetime.now(timezone.utc)
        sample_session.operator_id = a.id
        sample_session.last_client_msg_at = now - timedelta(hours=5)
        # operador leyo despues del mensaje
        sample_session.operator_last_read_at = now - timedelta(hours=1)
        await ho_db.commit()
        rows = await find_breached_sessions(ho_db, now, 4)
        assert rows == []

    async def test_recent_client_msg_not_breached(self, ho_db, agents_ab, sample_session):
        a, _ = agents_ab
        now = datetime.now(timezone.utc)
        sample_session.operator_id = a.id
        sample_session.last_client_msg_at = now - timedelta(minutes=30)
        await ho_db.commit()
        rows = await find_breached_sessions(ho_db, now, 4)
        assert rows == []

    async def test_breached_found(self, ho_db, agents_ab, sample_session):
        a, _ = agents_ab
        now = datetime.now(timezone.utc)
        sample_session.operator_id = a.id
        sample_session.last_client_msg_at = now - timedelta(hours=5)
        await ho_db.commit()
        rows = await find_breached_sessions(ho_db, now, 4)
        assert len(rows) == 1
        assert rows[0].id == sample_session.id

    async def test_cooldown_excludes_recent_handoff(self, ho_db, agents_ab, sample_session):
        a, _ = agents_ab
        now = datetime.now(timezone.utc)
        sample_session.operator_id = a.id
        sample_session.last_client_msg_at = now - timedelta(hours=5)
        # handoff reciente (1h atras < threshold 4h)
        sample_session.last_handoff_at = now - timedelta(hours=1)
        await ho_db.commit()
        rows = await find_breached_sessions(ho_db, now, 4)
        assert rows == []

    async def test_closed_session_not_found(self, ho_db, agents_ab, sample_session):
        a, _ = agents_ab
        now = datetime.now(timezone.utc)
        sample_session.operator_id = a.id
        sample_session.last_client_msg_at = now - timedelta(hours=5)
        sample_session.state = "closed"
        await ho_db.commit()
        rows = await find_breached_sessions(ho_db, now, 4)
        assert rows == []


class TestHandoffSession:
    async def test_noop_without_operator(self, ho_db, sample_session):
        result = await handoff_session(ho_db, sample_session)
        assert result == "noop"
        assert sample_session.operator_id is None

    async def test_released_when_no_other_candidate(
        self, ho_db, agents_ab, sample_session
    ):
        """A asignado, B inexistente en pool -> release."""
        a, _ = agents_ab
        sample_session.operator_id = a.id
        await ho_db.commit()
        await save_aa_config(ho_db, {
            "enabled": True, "strategy": "round_robin",
            "pool_user_ids": [a.id],
        })
        now = datetime.now(timezone.utc)
        result = await handoff_session(ho_db, sample_session, now=now)
        assert result == "released"
        assert sample_session.operator_id is None
        assert sample_session.last_handoff_at == now
        # verifica mensaje sistema
        msgs = (await ho_db.execute(
            select(Message).where(Message.session_id == sample_session.id)
        )).scalars().all()
        assert any("Liberado al pool" in (m.body or "") for m in msgs)

    async def test_reassigns_to_other_operator(
        self, ho_db, agents_ab, sample_session
    ):
        """A asignado, B disponible -> reasigna a B."""
        a, b = agents_ab
        sample_session.operator_id = a.id
        await ho_db.commit()
        await save_aa_config(ho_db, {
            "enabled": True, "strategy": "round_robin",
            "pool_user_ids": [a.id, b.id],
        })
        now = datetime.now(timezone.utc)
        result = await handoff_session(ho_db, sample_session, now=now)
        assert result == "reassigned"
        assert sample_session.operator_id == b.id
        assert sample_session.last_handoff_at == now
        msgs = (await ho_db.execute(
            select(Message).where(Message.session_id == sample_session.id)
        )).scalars().all()
        assert any("Reasignado por timeout SLA" in (m.body or "") for m in msgs)

    async def test_respects_on_duty_filter(
        self, ho_db, agents_ab, sample_session
    ):
        """A asignado, B off-duty -> release (B no es candidato)."""
        a, b = agents_ab
        # B solo lunes, ahora miercoles
        ho_db.add(OperatorSchedule(
            user_id=b.id, weekday=0,
            start_time=time(9, 0), end_time=time(17, 0),
        ))
        sample_session.operator_id = a.id
        await ho_db.commit()
        await save_aa_config(ho_db, {
            "enabled": True, "strategy": "round_robin",
            "pool_user_ids": [a.id, b.id],
        })
        now = datetime.now(timezone.utc)
        with patch(
            "app.services.operator_availability.now_local",
            return_value=_wed_14pm(),
        ):
            result = await handoff_session(ho_db, sample_session, now=now)
        assert result == "released"
        assert sample_session.operator_id is None

    async def test_excludes_current_operator_from_pick(
        self, ho_db, agents_ab, sample_session
    ):
        """A asignado y unico en pool -> release (no se reasigna a si mismo)."""
        a, _b = agents_ab
        sample_session.operator_id = a.id
        await ho_db.commit()
        await save_aa_config(ho_db, {
            "enabled": True, "strategy": "round_robin",
            "pool_user_ids": [a.id],
        })
        now = datetime.now(timezone.utc)
        result = await handoff_session(ho_db, sample_session, now=now)
        assert result == "released"
        assert sample_session.operator_id is None

    async def test_push_called_on_reassign(
        self, ho_db, agents_ab, sample_session
    ):
        a, b = agents_ab
        sample_session.operator_id = a.id
        await ho_db.commit()
        await save_aa_config(ho_db, {
            "enabled": True, "strategy": "round_robin",
            "pool_user_ids": [a.id, b.id],
        })
        mock_push = AsyncMock(return_value=1)
        with patch("app.services.webpush.send_push_to_user", new=mock_push):
            result = await handoff_session(ho_db, sample_session)
        assert result == "reassigned"
        mock_push.assert_called_once()
        args = mock_push.call_args
        assert args.args[1] == b.id  # user_id del nuevo operador
