"""Tests E2E del handler `_try_handle_operator_topic_reply` con media.

Simula el flujo completo cuando Telegram entrega un webhook con una foto
o documento dentro de un topic del grupo hub de operadores:

- `_resolve_hub_group_id` devuelve el group_id configurado
- `find_session_by_topic` encuentra la sesión por (group_id, topic_id)
- Operador autorizado (User.telegram_user_id coincide)
- Se descarga el media de TG vía `_download_telegram_file`
- Se reenvía a WA del cliente via `send_whatsapp_media_bytes`
- Se registran los Message outbound (WA) + inbound (TG log)
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.services.messaging import _try_handle_operator_topic_reply


@pytest_asyncio.fixture
async def operator_user(db):
    from app.models.user import User
    u = User(
        email="op@test.com",
        hashed_password="x",
        full_name="Operador Test",
        role="cotizador",
        is_active=True,
        telegram_user_id="999888",
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def session_with_topic(db, sample_session):
    """Sesión con ventana abierta y ligada a un topic TG."""
    sample_session.state = "active"
    sample_session.tg_group_id = "-100555"
    sample_session.tg_topic_id = 42
    sample_session.last_client_msg_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(sample_session)
    return sample_session


@pytest.fixture
def external_mocks():
    """Mocks compartidos: hub_group, token, instance, HTTP clients externos."""
    with patch("app.services.messaging._resolve_hub_group_id",
               new=AsyncMock(return_value="-100555")), \
         patch("app.services.messaging._resolve_telegram_token",
               new=AsyncMock(return_value="fake-token")), \
         patch("app.services.messaging._resolve_wa_instance",
               new=AsyncMock(return_value={
                   "url": "http://evo", "instance_name": "apu", "api_key": "k",
               })), \
         patch("app.services.messaging.send_whatsapp_media_bytes",
               new=AsyncMock(return_value=True)) as mock_send_media, \
         patch("app.services.messaging.send_telegram",
               new=AsyncMock(return_value=True)) as mock_send_tg, \
         patch("app.services.messaging._download_telegram_file",
               new=AsyncMock(return_value=(b"\x89PNG\r\nfakebytes", "photos/x.jpg"))) as mock_dl:
        yield {
            "send_media": mock_send_media,
            "send_tg": mock_send_tg,
            "download": mock_dl,
        }


class TestOperatorPhotoE2E:
    async def test_photo_relayed_to_client_wa(
        self, db, session_with_topic, operator_user, external_mocks,
    ):
        """Operador sube foto al topic → se descarga de TG y reenvía a WA."""
        inner_send = external_mocks["send_media"]
        tg_msg = {
            "message_id": 777,
            "chat": {"id": "-100555"},
            "from": {"id": 999888, "username": "operador1"},
            "message_thread_id": 42,
            "photo": [
                {"file_id": "AgACsmall", "file_size": 100},
                {"file_id": "AgAClarge", "file_size": 5000},
            ],
            "caption": "Aquí la cotización firmada",
        }

        handled = await _try_handle_operator_topic_reply(
            db,
            chat_id="-100555",
            message_thread_id=42,
            from_user_id="999888",
            username="operador1",
            text="Aquí la cotización firmada",
            has_photo=True,
            has_document=False,
            msg=tg_msg,
            ext_msg_id="777",
        )

        assert handled is True

        # Se descargó el archivo con el file_id de mayor resolución (último)
        external_mocks["download"].assert_called_once_with("AgAClarge")

        # Se envió a WA con los args correctos
        inner_send.assert_called_once()
        args = inner_send.call_args[0]
        assert args[0] == "59171234567"  # phone
        assert args[1] == b"\x89PNG\r\nfakebytes"  # content
        assert args[2] == "image/jpeg"  # mime (default de foto TG)
        assert args[3] == "foto.jpg"  # filename
        assert args[4] == "Aquí la cotización firmada"  # caption

        # Se registraron 2 Messages: outbound (WA) + inbound (TG log)
        from sqlalchemy import select
        from app.models.conversation import Message
        msgs = (await db.execute(
            select(Message).where(Message.session_id == session_with_topic.id).order_by(Message.id)
        )).scalars().all()
        assert len(msgs) == 2
        out = msgs[0]
        inb = msgs[1]
        assert out.direction == "outbound" and out.channel == "whatsapp"
        assert out.media_type == "image"
        assert out.sender_type == "operator"
        assert inb.direction == "inbound" and inb.channel == "telegram"
        assert inb.media_type == "photo"
        assert inb.ext_message_id == "777"

        # Estado transicionó a operator_engaged
        await db.refresh(session_with_topic)
        assert session_with_topic.state == "operator_engaged"


class TestOperatorDocumentE2E:
    async def test_pdf_relayed_with_filename_and_mime(
        self, db, session_with_topic, operator_user, external_mocks,
    ):
        inner_send = external_mocks["send_media"]
        tg_msg = {
            "message_id": 888,
            "chat": {"id": "-100555"},
            "from": {"id": 999888, "username": "operador1"},
            "message_thread_id": 42,
            "document": {
                "file_id": "DOC123",
                "file_name": "cotizacion-PED-0001.pdf",
                "mime_type": "application/pdf",
            },
            "caption": "",
        }

        handled = await _try_handle_operator_topic_reply(
            db,
            chat_id="-100555",
            message_thread_id=42,
            from_user_id="999888",
            username="operador1",
            text="",
            has_photo=False,
            has_document=True,
            msg=tg_msg,
            ext_msg_id="888",
        )
        assert handled is True
        external_mocks["download"].assert_called_once_with("DOC123")
        args = inner_send.call_args[0]
        assert args[2] == "application/pdf"
        assert args[3] == "cotizacion-PED-0001.pdf"

        from sqlalchemy import select
        from app.models.conversation import Message
        msgs = (await db.execute(
            select(Message).where(Message.session_id == session_with_topic.id).order_by(Message.id)
        )).scalars().all()
        assert len(msgs) == 2
        # outbound es document (mapeado desde application/pdf)
        assert msgs[0].media_type == "document"
        assert msgs[1].media_type == "document"


class TestFallbackWhenDownloadFails:
    async def test_fallback_to_text_when_tg_download_returns_none(
        self, db, session_with_topic, operator_user,
    ):
        """Si _download_telegram_file falla, se cae al aviso de texto."""
        with patch("app.services.messaging._resolve_hub_group_id",
                   new=AsyncMock(return_value="-100555")), \
             patch("app.services.messaging._resolve_telegram_token",
                   new=AsyncMock(return_value="fake")), \
             patch("app.services.messaging._download_telegram_file",
                   new=AsyncMock(return_value=None)), \
             patch("app.services.conversation_hub.send_whatsapp",
                   new=AsyncMock(return_value=True)) as fallback_wa, \
             patch("app.services.messaging.send_telegram",
                   new=AsyncMock(return_value=True)) as mock_tg, \
             patch("app.services.messaging.send_whatsapp_media_bytes",
                   new=AsyncMock(return_value=False)) as inner_send:
            tg_msg = {
                "message_id": 999,
                "chat": {"id": "-100555"},
                "from": {"id": 999888, "username": "operador1"},
                "message_thread_id": 42,
                "photo": [{"file_id": "X", "file_size": 1}],
            }
            handled = await _try_handle_operator_topic_reply(
                db,
                chat_id="-100555",
                message_thread_id=42,
                from_user_id="999888",
                username="operador1",
                text="nota",
                has_photo=True,
                has_document=False,
                msg=tg_msg,
                ext_msg_id="999",
            )
            assert handled is True
            # No se llamó a send_whatsapp_media_bytes (descarga falló)
            inner_send.assert_not_called()
            # Fallback envió texto por WA ("El equipo te envió una foto...")
            fallback_wa.assert_called_once()
            call_text = fallback_wa.call_args[0][1]
            assert "foto" in call_text.lower()
            assert "portal" in call_text.lower()
            # Y se avisó al topic con el mensaje de warning
            any_warn = any(
                "No pude reenviar" in str(c) for c in mock_tg.call_args_list
            )
            assert any_warn

        # Deben haberse registrado 2 Messages: outbound fallback + inbound log
        from sqlalchemy import select
        from app.models.conversation import Message
        msgs = (await db.execute(
            select(Message).where(Message.session_id == session_with_topic.id).order_by(Message.id)
        )).scalars().all()
        assert len(msgs) == 2

    async def test_unauthorized_operator_gets_warning(
        self, db, session_with_topic, external_mocks,
    ):
        """Un tg_user_id sin User registrado no reenvía nada."""
        tg_msg = {
            "message_id": 1,
            "chat": {"id": "-100555"},
            "from": {"id": 111222, "username": "intruso"},
            "message_thread_id": 42,
            "photo": [{"file_id": "X", "file_size": 1}],
        }
        handled = await _try_handle_operator_topic_reply(
            db,
            chat_id="-100555",
            message_thread_id=42,
            from_user_id="111222",
            username="intruso",
            text="",
            has_photo=True,
            has_document=False,
            msg=tg_msg,
            ext_msg_id="1",
        )
        assert handled is True
        # No se llamó a download ni send_media
        external_mocks["download"].assert_not_called()
        external_mocks["send_media"].assert_not_called()
        # Sí se avisó al topic que no está registrado
        warned = any(
            "no está registrado" in str(c) for c in external_mocks["send_tg"].call_args_list
        )
        assert warned


class TestUnknownTopicIgnored:
    async def test_topic_without_session_returns_false(
        self, db, sample_session, external_mocks,
    ):
        """Si el topic_id no coincide con ninguna sesión, handler devuelve False."""
        # sample_session no tiene tg_topic_id seteado
        tg_msg = {
            "message_id": 1,
            "chat": {"id": "-100555"},
            "from": {"id": 999888},
            "message_thread_id": 99999,
            "photo": [{"file_id": "X"}],
        }
        handled = await _try_handle_operator_topic_reply(
            db,
            chat_id="-100555",
            message_thread_id=99999,
            from_user_id="999888",
            username="x",
            text="",
            has_photo=True,
            has_document=False,
            msg=tg_msg,
            ext_msg_id="1",
        )
        assert handled is False
        external_mocks["download"].assert_not_called()

    async def test_wrong_hub_group_returns_false(self, db, session_with_topic):
        """Si el chat_id no es el hub_group configurado, handler devuelve False."""
        with patch("app.services.messaging._resolve_hub_group_id",
                   new=AsyncMock(return_value="-100OTHER")), \
             patch("app.services.messaging._download_telegram_file",
                   new=AsyncMock(return_value=(b"x", "p"))) as mock_dl:
            handled = await _try_handle_operator_topic_reply(
                db,
                chat_id="-100555",
                message_thread_id=42,
                from_user_id="999888",
                username="x",
                text="",
                has_photo=True,
                has_document=False,
                msg={"photo": [{"file_id": "X"}]},
                ext_msg_id="1",
            )
            assert handled is False
            mock_dl.assert_not_called()
