"""Tests end-to-end del flujo de WhatsApp.

Simula el ciclo completo:
1. Cliente envía primer mensaje → ventana 24h se abre, estado → active
2. Bot responde con plantilla
3. Operador responde desde web/TG → estado → operator_engaged
4. Ventana cerrada (>24h) → operador no puede enviar por WA
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.services.conversation_hub import (
    mirror_operator_to_client,
    bot_autoreply,
    is_wa_window_open,
    record_message,
    deliver_quote_to_client,
)


@pytest.fixture
def mock_external_apis():
    """Evita llamadas reales a Evolution / Telegram / SMTP."""
    with patch("app.services.conversation_hub.send_whatsapp", new=AsyncMock(return_value=True)) as wa, \
         patch("app.services.conversation_hub.send_telegram", new=AsyncMock(return_value=True)) as tg, \
         patch("app.services.conversation_hub.send_email", new=AsyncMock(return_value=True)) as email:
        yield {"wa": wa, "tg": tg, "email": email}


class TestOperatorReplyWithinWindow:
    async def test_operator_reply_sends_when_window_open(self, db, sample_session, mock_external_apis):
        # Cliente acaba de escribir
        sample_session.state = "active"
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()

        ok = await mirror_operator_to_client(db, sample_session, "Hola, te cotizo")
        assert ok is True
        mock_external_apis["wa"].assert_called_once()
        call_args = mock_external_apis["wa"].call_args
        # phone, text
        assert call_args[0][0] == "59171234567"
        assert call_args[0][1] == "Hola, te cotizo"

        # Estado transitó a operator_engaged
        await db.refresh(sample_session)
        assert sample_session.state == "operator_engaged"
        assert sample_session.last_operator_msg_at is not None

    async def test_operator_reply_blocked_when_window_closed(self, db, sample_session, mock_external_apis):
        # Cliente escribió hace 48h
        sample_session.state = "active"
        sample_session.last_client_msg_at = datetime.now(timezone.utc) - timedelta(hours=48)
        await db.commit()

        ok = await mirror_operator_to_client(db, sample_session, "Hola tarde")
        assert ok is False
        # No se llamó a send_whatsapp
        mock_external_apis["wa"].assert_not_called()

    async def test_operator_reply_blocked_without_client_phone(self, db, sample_session, mock_external_apis):
        sample_session.client_phone = None
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()

        ok = await mirror_operator_to_client(db, sample_session, "Hola")
        assert ok is False
        mock_external_apis["wa"].assert_not_called()

    async def test_operator_reply_blocked_without_prior_client_msg(self, db, sample_session, mock_external_apis):
        """Sin mensaje previo del cliente NO hay ventana abierta (no se puede iniciar)."""
        assert sample_session.last_client_msg_at is None
        ok = await mirror_operator_to_client(db, sample_session, "Iniciando conversación")
        assert ok is False
        mock_external_apis["wa"].assert_not_called()


class TestBotAutoreply:
    async def test_silent_when_operator_engaged(self, db, sample_session, mock_external_apis):
        sample_session.state = "operator_engaged"
        await db.commit()
        reply = await bot_autoreply(db, sample_session, "Hola")
        assert reply is None

    async def test_reply_when_waiting_first_contact(self, db, sample_session, mock_external_apis):
        # sample_session está en waiting_first_contact por default
        reply = await bot_autoreply(db, sample_session, "Hola")
        assert reply is not None
        assert "PED-0001" in reply or "solicitud" in reply.lower() or "pedido" in reply.lower()

    async def test_reply_when_active(self, db, sample_session, mock_external_apis):
        sample_session.state = "active"
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()
        reply = await bot_autoreply(db, sample_session, "Hola, confirmo")
        assert reply is not None

    async def test_attention_keyword_pings_operators(self, db, sample_session, mock_external_apis):
        """Mensaje con 'urgente' debería pingear al topic si hay grupo/topic."""
        sample_session.tg_group_id = "-100123"
        sample_session.tg_topic_id = 42
        sample_session.state = "active"
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()

        await bot_autoreply(db, sample_session, "Necesito urgente saber el precio")
        # send_telegram debería haberse llamado al menos una vez (el ping)
        assert mock_external_apis["tg"].call_count >= 1
        # Al menos una de las llamadas debe contener "Atención"
        any_ping = any("Atención" in str(call) for call in mock_external_apis["tg"].call_args_list)
        assert any_ping, f"Ninguna llamada pingeó con 'Atención'. Calls: {mock_external_apis['tg'].call_args_list}"

    async def test_quote_sent_state_replies_with_hint(self, db, sample_session, mock_external_apis):
        sample_session.tg_group_id = "-100123"
        sample_session.tg_topic_id = 42
        sample_session.state = "quote_sent"
        await db.commit()
        reply = await bot_autoreply(db, sample_session, "y cuando me llega?")
        assert reply is not None
        assert "cotización" in reply.lower() or "cotizacion" in reply.lower()


class TestFullCycle:
    """Simula el ciclo completo de una conversación."""

    async def test_full_happy_path(self, db, sample_session, mock_external_apis):
        # 1. Cliente envía primer mensaje
        assert sample_session.state == "waiting_first_contact"
        assert is_wa_window_open(sample_session) is False  # aún no escribió

        # Simular handle_whatsapp_message:
        if sample_session.state == "waiting_first_contact":
            sample_session.state = "active"
        await record_message(
            db, sample_session,
            direction="inbound", channel="whatsapp",
            sender_type="client", sender_ref="59171234567",
            body="Hola, confirmo pedido PED-0001",
        )
        await db.commit()
        # NOTA: no hacemos db.refresh(sample_session) para evitar que SQLite
        # devuelva last_client_msg_at naive. En Postgres con asyncpg los
        # DateTime(timezone=True) llegan tz-aware.

        assert sample_session.state == "active"
        assert is_wa_window_open(sample_session) is True  # ventana abierta

        # 2. Bot autoreply
        reply = await bot_autoreply(db, sample_session, "Hola, confirmo pedido PED-0001")
        assert reply is not None

        # 3. Operador responde
        ok = await mirror_operator_to_client(db, sample_session, "Hola! Te cotizo ya")
        assert ok is True
        assert sample_session.state == "operator_engaged"

        # 4. Bot queda silencioso mientras operator_engaged
        reply2 = await bot_autoreply(db, sample_session, "Gracias")
        assert reply2 is None

        # 5. Simular que pasan >24h sin mensaje del cliente
        sample_session.last_client_msg_at = datetime.now(timezone.utc) - timedelta(hours=25)
        await db.commit()
        assert is_wa_window_open(sample_session) is False

        # 6. Operador intenta responder: falla (ventana cerrada)
        ok = await mirror_operator_to_client(db, sample_session, "Otra cosa")
        assert ok is False

    async def test_window_survives_naive_datetime_from_db(self, db, sample_session, mock_external_apis):
        """Verifica que is_wa_window_open tolere naive datetimes del driver.

        SQLite devuelve DateTime(timezone=True) como naive; la función debe
        asumir UTC y no crashear. Postgres+asyncpg normalmente los devuelve
        tz-aware, pero el guard protege contra configs atípicas.
        """
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(sample_session)

        # Independiente de si el driver devuelve aware o naive, debe funcionar
        assert is_wa_window_open(sample_session) is True

    async def test_message_log_is_ordered(self, db, sample_session, mock_external_apis):
        sample_session.state = "active"
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()

        await record_message(
            db, sample_session, direction="inbound", channel="whatsapp",
            sender_type="client", body="msg1",
        )
        await record_message(
            db, sample_session, direction="outbound", channel="whatsapp",
            sender_type="bot", body="bot reply",
        )
        await mirror_operator_to_client(db, sample_session, "op reply")
        await db.commit()

        # Fetch messages
        from sqlalchemy import select
        from app.models.conversation import Message
        msgs = (await db.execute(
            select(Message).where(Message.session_id == sample_session.id).order_by(Message.id)
        )).scalars().all()
        assert len(msgs) == 3
        assert msgs[0].body == "msg1"
        assert msgs[1].body == "bot reply"
        assert msgs[2].body == "op reply"
        assert msgs[2].sender_type == "operator"
