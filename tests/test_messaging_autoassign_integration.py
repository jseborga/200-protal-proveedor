"""Tests de integracion: hook de auto-asignacion en handle_whatsapp_message.

Verifica que cuando entra un mensaje WhatsApp para una sesion sin
operador:
- Si auto_assign esta activa, `handle_whatsapp_message` dispara el hook
  y deja la sesion con operator_id seteado.
- Si auto_assign esta inactiva, la sesion queda sin operator_id.
- Si la sesion ya tiene operator_id, no se reasigna.
- Se registra el Message de sistema con el prefijo esperado.

Se mockean todas las llamadas de red (send_whatsapp, send_telegram*,
get_whatsapp_media_from_evolution, send_push_to_user) para aislar el
flujo al comportamiento local del DB + hook.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from unittest.mock import AsyncMock, patch

import pytest_asyncio
from sqlalchemy import JSON, select

from app.models.conversation import ConversationSession, Message
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services.inbox_autoassign import save_config


@pytest_asyncio.fixture
async def integ_db(db):
    """Anade mkt_system_setting al engine SQLite del fixture db."""
    SystemSetting.__table__.c.value.type = JSON()
    eng = db.bind
    async with eng.begin() as conn:
        await conn.run_sync(
            lambda sc: SystemSetting.__table__.create(sc, checkfirst=True)
        )
    return db


@pytest_asyncio.fixture
async def operators(integ_db) -> list[User]:
    users = []
    for i, name in enumerate(["Op A", "Op B"]):
        u = User(
            email=f"op{i}@test.com",
            hashed_password="x",
            full_name=name,
            role="field_agent",
            is_active=True,
        )
        integ_db.add(u)
        users.append(u)
    await integ_db.commit()
    for u in users:
        await integ_db.refresh(u)
    return users


@pytest_asyncio.fixture
async def open_session(integ_db, sample_pedido) -> ConversationSession:
    """Sesion activa sin operator_id, sin topic TG (para que mirror salga temprano)."""
    s = ConversationSession(
        pedido_id=sample_pedido.id,
        client_user_id=sample_pedido.created_by,
        client_phone="59171234567",
        state="active",
        # tg_group_id/tg_topic_id = None -> mirror_client_to_topic no-op
    )
    integ_db.add(s)
    await integ_db.commit()
    await integ_db.refresh(s)
    return s


def _wa_msg(phone: str, text: str) -> dict:
    """Construir un payload Evolution API tipico para un mensaje de texto."""
    return {
        "key": {"remoteJid": f"{phone}@s.whatsapp.net", "id": "abc123"},
        "message": {"conversation": text},
    }


# ──────────────────────────────────────────────────────────────────
# Integracion del hook
# ──────────────────────────────────────────────────────────────────
class TestAutoAssignHook:
    async def test_assigns_on_first_inbound_when_enabled(
        self, integ_db, operators, open_session
    ):
        await save_config(integ_db, {"enabled": True, "strategy": "round_robin"})

        with patch("app.services.messaging.send_whatsapp", new=AsyncMock(return_value=True)), \
             patch("app.services.messaging.get_whatsapp_media_from_evolution", new=AsyncMock(return_value=None)), \
             patch("app.services.webpush.send_push_to_user", new=AsyncMock(return_value=0)):
            from app.services.messaging import handle_whatsapp_message
            await handle_whatsapp_message(
                integ_db, _wa_msg("59171234567", "hola, necesito cemento")
            )

        await integ_db.refresh(open_session)
        assert open_session.operator_id == operators[0].id

        # Verificar mensaje de sistema
        msgs = (await integ_db.execute(
            select(Message).where(
                Message.session_id == open_session.id,
                Message.sender_type == "system",
            )
        )).scalars().all()
        assert len(msgs) == 1
        assert "Auto-asignado" in (msgs[0].body or "")

    async def test_no_assignment_when_disabled(
        self, integ_db, operators, open_session
    ):
        # save_config -> enabled=False (default)
        await save_config(integ_db, {"enabled": False})

        with patch("app.services.messaging.send_whatsapp", new=AsyncMock(return_value=True)), \
             patch("app.services.messaging.get_whatsapp_media_from_evolution", new=AsyncMock(return_value=None)), \
             patch("app.services.webpush.send_push_to_user", new=AsyncMock(return_value=0)):
            from app.services.messaging import handle_whatsapp_message
            await handle_whatsapp_message(
                integ_db, _wa_msg("59171234567", "hola")
            )

        await integ_db.refresh(open_session)
        assert open_session.operator_id is None

        sys_msgs = (await integ_db.execute(
            select(Message).where(
                Message.session_id == open_session.id,
                Message.sender_type == "system",
            )
        )).scalars().all()
        assert sys_msgs == []

    async def test_no_reassignment_when_already_assigned(
        self, integ_db, operators, open_session
    ):
        # Asignar manualmente al operator B antes del inbound
        open_session.operator_id = operators[1].id
        await integ_db.commit()

        await save_config(integ_db, {"enabled": True, "strategy": "round_robin"})

        with patch("app.services.messaging.send_whatsapp", new=AsyncMock(return_value=True)), \
             patch("app.services.messaging.get_whatsapp_media_from_evolution", new=AsyncMock(return_value=None)), \
             patch("app.services.webpush.send_push_to_user", new=AsyncMock(return_value=0)):
            from app.services.messaging import handle_whatsapp_message
            await handle_whatsapp_message(
                integ_db, _wa_msg("59171234567", "hola")
            )

        await integ_db.refresh(open_session)
        # Sigue siendo el B, no rotado al A
        assert open_session.operator_id == operators[1].id

        # No debe haber mensaje de sistema "Auto-asignado"
        sys_msgs = (await integ_db.execute(
            select(Message).where(
                Message.session_id == open_session.id,
                Message.sender_type == "system",
            )
        )).scalars().all()
        assert sys_msgs == []

    async def test_webpush_fires_with_newly_assigned_operator(
        self, integ_db, operators, open_session
    ):
        """Despues del auto-assign, el hook webpush debe ejecutarse con el
        operator_id recien seteado (verificamos con un mock)."""
        await save_config(integ_db, {"enabled": True, "strategy": "round_robin"})

        push_mock = AsyncMock(return_value=0)
        with patch("app.services.messaging.send_whatsapp", new=AsyncMock(return_value=True)), \
             patch("app.services.messaging.get_whatsapp_media_from_evolution", new=AsyncMock(return_value=None)), \
             patch("app.services.webpush.send_push_to_user", new=push_mock):
            from app.services.messaging import handle_whatsapp_message
            await handle_whatsapp_message(
                integ_db, _wa_msg("59171234567", "urgente, precio?")
            )

        # El webpush se llamo exactamente una vez con user_id = operator A
        assert push_mock.await_count == 1
        call_args = push_mock.await_args
        assert call_args.args[1] == operators[0].id  # send_push_to_user(db, user_id, payload)
        payload = call_args.args[2]
        assert "urgente" in payload["body"].lower()
        assert payload["session_id"] == open_session.id

    async def test_least_loaded_strategy_picks_less_busy(
        self, integ_db, operators, open_session, sample_pedido
    ):
        """Si A ya tiene 1 sesion abierta, least_loaded debe elegir a B."""
        # Dar a A una sesion abierta previa
        busy = ConversationSession(
            pedido_id=sample_pedido.id, client_phone="1",
            state="active", operator_id=operators[0].id,
        )
        integ_db.add(busy)
        await integ_db.commit()

        await save_config(integ_db, {"enabled": True, "strategy": "least_loaded"})

        with patch("app.services.messaging.send_whatsapp", new=AsyncMock(return_value=True)), \
             patch("app.services.messaging.get_whatsapp_media_from_evolution", new=AsyncMock(return_value=None)), \
             patch("app.services.webpush.send_push_to_user", new=AsyncMock(return_value=0)):
            from app.services.messaging import handle_whatsapp_message
            await handle_whatsapp_message(
                integ_db, _wa_msg("59171234567", "consulta")
            )

        await integ_db.refresh(open_session)
        assert open_session.operator_id == operators[1].id
