"""Tests para is_wa_window_open — validación de la ventana 24h de WhatsApp.

Regla de WA Business: solo se puede enviar texto libre al cliente dentro de
las 24h posteriores a su último mensaje. Pasado eso, solo plantillas aprobadas.
"""
from datetime import datetime, timezone, timedelta

import pytest

from app.models.conversation import ConversationSession
from app.services.conversation_hub import is_wa_window_open, WA_WINDOW_HOURS


def _make_session(last_client_msg_at=None, tzinfo=timezone.utc):
    """Build a lightweight ConversationSession object for window tests."""
    s = ConversationSession(
        pedido_id=1,
        state="active",
        client_phone="59171234567",
    )
    s.last_client_msg_at = last_client_msg_at
    return s


class TestWaWindowOpen:
    def test_no_client_msg_window_closed(self):
        """Sin mensaje del cliente nunca se abrió la ventana."""
        s = _make_session(last_client_msg_at=None)
        assert is_wa_window_open(s) is False

    def test_just_received_message_window_open(self):
        """Mensaje recién recibido → ventana abierta."""
        now = datetime.now(timezone.utc)
        s = _make_session(last_client_msg_at=now)
        assert is_wa_window_open(s) is True

    def test_1_hour_ago_open(self):
        now = datetime.now(timezone.utc)
        s = _make_session(last_client_msg_at=now - timedelta(hours=1))
        assert is_wa_window_open(s) is True

    def test_23_hours_ago_open(self):
        now = datetime.now(timezone.utc)
        s = _make_session(last_client_msg_at=now - timedelta(hours=23))
        assert is_wa_window_open(s) is True

    def test_23h_59m_ago_open(self):
        now = datetime.now(timezone.utc)
        s = _make_session(last_client_msg_at=now - timedelta(hours=23, minutes=59))
        assert is_wa_window_open(s) is True

    def test_exactly_24h_closed(self):
        """Exactamente 24h es el límite inclusivo → cerrado (usa <)."""
        now = datetime.now(timezone.utc)
        s = _make_session(last_client_msg_at=now - timedelta(hours=24))
        # La implementación usa `delta < timedelta(hours=24)`, así que ==24h falla
        assert is_wa_window_open(s) is False

    def test_25_hours_ago_closed(self):
        now = datetime.now(timezone.utc)
        s = _make_session(last_client_msg_at=now - timedelta(hours=25))
        assert is_wa_window_open(s) is False

    def test_7_days_ago_closed(self):
        now = datetime.now(timezone.utc)
        s = _make_session(last_client_msg_at=now - timedelta(days=7))
        assert is_wa_window_open(s) is False


class TestWaWindowConstant:
    def test_window_hours_is_24(self):
        """WhatsApp Business window must be exactly 24h as per Meta policy."""
        assert WA_WINDOW_HOURS == 24


class TestWaWindowNaiveDatetime:
    """is_wa_window_open debe tolerar datetimes naive (asumiendo UTC).

    Algunos drivers o configs devuelven DateTime(timezone=True) como naive;
    la función asume UTC en ese caso para no crashear con TypeError.
    """

    def test_naive_datetime_recent_open(self):
        # Naive, asumido UTC → ventana abierta
        naive = datetime.now(timezone.utc).replace(tzinfo=None)
        s = _make_session(last_client_msg_at=naive)
        assert is_wa_window_open(s) is True

    def test_naive_datetime_old_closed(self):
        naive_old = (datetime.now(timezone.utc) - timedelta(hours=48)).replace(tzinfo=None)
        s = _make_session(last_client_msg_at=naive_old)
        assert is_wa_window_open(s) is False
