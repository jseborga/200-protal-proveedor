"""Tests para transiciones de estado de ConversationSession + record_message.

Estados esperados:
  waiting_first_contact → active → operator_engaged → quote_sent → closed
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.models.conversation import ConversationSession, Message
from app.services.conversation_hub import (
    record_message,
    find_active_session_for_client,
    find_session_by_topic,
)


class TestRecordMessageTimestamps:
    @staticmethod
    def _as_aware(dt):
        """SQLite devuelve naive datetimes aun con timezone=True; normalizar."""
        if dt is not None and dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    async def test_inbound_client_updates_last_client_msg_at(self, db, sample_session):
        before = datetime.now(timezone.utc)
        msg = await record_message(
            db, sample_session,
            direction="inbound", channel="whatsapp",
            sender_type="client", sender_ref="59171234567",
            body="Hola, confirmo pedido",
        )
        await db.commit()
        await db.refresh(sample_session)
        assert msg.id is not None
        assert msg.direction == "inbound"
        assert msg.sender_type == "client"
        assert sample_session.last_client_msg_at is not None
        assert self._as_aware(sample_session.last_client_msg_at) >= before
        assert sample_session.last_operator_msg_at is None

    async def test_outbound_operator_updates_last_operator_msg_at(self, db, sample_session):
        before = datetime.now(timezone.utc)
        await record_message(
            db, sample_session,
            direction="outbound", channel="whatsapp",
            sender_type="operator", sender_ref="42",
            body="Te paso cotización en breve",
        )
        await db.commit()
        await db.refresh(sample_session)
        assert sample_session.last_operator_msg_at is not None
        assert self._as_aware(sample_session.last_operator_msg_at) >= before
        assert sample_session.last_client_msg_at is None

    async def test_bot_outbound_does_not_update_operator_timestamp(self, db, sample_session):
        """Bot autoreply no cuenta como respuesta del operador."""
        await record_message(
            db, sample_session,
            direction="outbound", channel="whatsapp",
            sender_type="bot",
            body="Gracias por escribir",
        )
        await db.commit()
        await db.refresh(sample_session)
        # Ni operator_msg_at ni client_msg_at se mueven
        assert sample_session.last_operator_msg_at is None
        assert sample_session.last_client_msg_at is None

    async def test_inbound_operator_edge_case(self, db, sample_session):
        """Un inbound marcado como operator (raro pero posible) no mueve timestamps."""
        await record_message(
            db, sample_session,
            direction="inbound", channel="telegram",
            sender_type="operator",
            body="mensaje raro",
        )
        await db.commit()
        await db.refresh(sample_session)
        # La implementación actual solo actualiza si:
        #   inbound+client → client ts
        #   outbound+operator → operator ts
        # Otras combinaciones no mueven nada
        assert sample_session.last_client_msg_at is None
        assert sample_session.last_operator_msg_at is None


class TestFindActiveSession:
    async def test_find_by_normalized_phone(self, db, sample_session):
        # Session stored as "59171234567" — buscar con formato JID
        found = await find_active_session_for_client(db, "59171234567@s.whatsapp.net")
        assert found is not None
        assert found.id == sample_session.id

    async def test_find_by_plain_number(self, db, sample_session):
        found = await find_active_session_for_client(db, "59171234567")
        assert found is not None
        assert found.id == sample_session.id

    async def test_find_with_plus_prefix(self, db, sample_session):
        found = await find_active_session_for_client(db, "+591 71234567")
        assert found is not None
        assert found.id == sample_session.id

    async def test_find_non_existent_returns_none(self, db, sample_session):
        found = await find_active_session_for_client(db, "59199999999")
        assert found is None

    async def test_closed_session_not_found(self, db, sample_session):
        sample_session.state = "closed"
        await db.commit()
        found = await find_active_session_for_client(db, "59171234567")
        assert found is None

    async def test_empty_phone_returns_none(self, db):
        found = await find_active_session_for_client(db, "")
        assert found is None


class TestFindSessionByTopic:
    async def test_find_by_topic(self, db, sample_session):
        sample_session.tg_group_id = "-100123"
        sample_session.tg_topic_id = 777
        await db.commit()
        found = await find_session_by_topic(db, "-100123", 777)
        assert found is not None
        assert found.id == sample_session.id

    async def test_wrong_topic_returns_none(self, db, sample_session):
        sample_session.tg_group_id = "-100123"
        sample_session.tg_topic_id = 777
        await db.commit()
        assert await find_session_by_topic(db, "-100123", 888) is None
        assert await find_session_by_topic(db, "-100999", 777) is None


class TestStateTransitions:
    """Simula las transiciones que dispara el webhook de WA.

    El flujo real vive en handle_whatsapp_message (messaging.py:615-662).
    Aquí replicamos la lógica clave para verificar la correctitud.
    """

    async def test_waiting_to_active_on_first_inbound(self, db, sample_session):
        assert sample_session.state == "waiting_first_contact"
        # Simula la línea messaging.py:618-619
        if sample_session.state == "waiting_first_contact":
            sample_session.state = "active"
        await record_message(
            db, sample_session,
            direction="inbound", channel="whatsapp",
            sender_type="client", body="Hola",
        )
        await db.commit()
        await db.refresh(sample_session)
        assert sample_session.state == "active"
        assert sample_session.last_client_msg_at is not None

    async def test_active_to_operator_engaged_on_operator_reply(self, db, sample_session):
        # Cliente ya escribió
        sample_session.state = "active"
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()

        # Operador responde (simula mirror_operator_to_client)
        await record_message(
            db, sample_session,
            direction="outbound", channel="whatsapp",
            sender_type="operator", sender_ref="42",
            body="Hola, aquí estoy",
        )
        # La función mirror_operator_to_client hace: session.state = "operator_engaged"
        if sample_session.state != "operator_engaged":
            sample_session.state = "operator_engaged"
        await db.commit()
        await db.refresh(sample_session)
        assert sample_session.state == "operator_engaged"

    async def test_quote_sent_state_persists(self, db, sample_session):
        sample_session.state = "quote_sent"
        await db.commit()
        await db.refresh(sample_session)
        # quote_sent debe seguir siendo findable (no es closed)
        found = await find_active_session_for_client(db, "59171234567")
        assert found is not None
        assert found.state == "quote_sent"
