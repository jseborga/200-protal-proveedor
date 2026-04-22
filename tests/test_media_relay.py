"""Tests para el relay de media operador→cliente (Fase 1.5).

Cubre:
- `_wa_mediatype_from_mime`: mapeo MIME → mediatype de Evolution
- `send_whatsapp_media_bytes`: payload correcto a Evolution sendMedia (base64)
- `mirror_operator_media_to_client`: respeta ventana 24h, client_phone,
  estado, registra Message con media_type, sube estado a operator_engaged
"""
import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/db")

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.messaging import _wa_mediatype_from_mime
from app.services.conversation_hub import mirror_operator_media_to_client


class TestWaMediatypeMapping:
    def test_image_png(self):
        assert _wa_mediatype_from_mime("image/png") == "image"

    def test_image_jpeg(self):
        assert _wa_mediatype_from_mime("image/jpeg") == "image"

    def test_video(self):
        assert _wa_mediatype_from_mime("video/mp4") == "video"

    def test_audio(self):
        assert _wa_mediatype_from_mime("audio/ogg") == "audio"

    def test_pdf_as_document(self):
        assert _wa_mediatype_from_mime("application/pdf") == "document"

    def test_none_as_document(self):
        assert _wa_mediatype_from_mime(None) == "document"

    def test_empty_as_document(self):
        assert _wa_mediatype_from_mime("") == "document"

    def test_case_insensitive(self):
        assert _wa_mediatype_from_mime("IMAGE/PNG") == "image"


class TestSendWhatsappMediaBytes:
    async def test_sends_base64_payload(self):
        """Verifica que se arma el payload con base64, mediatype y fileName."""
        from app.services import messaging as M

        captured = {}

        class _FakeResp:
            status_code = 201
            text = ""

            def json(self):
                return {"key": {"id": "abc"}}

        class _FakeClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, headers=None, json=None):
                captured["url"] = url
                captured["json"] = json
                captured["headers"] = headers
                return _FakeResp()

        async def _inst(_):
            return {"url": "http://evo", "instance_name": "apu", "api_key": "k"}

        with patch.object(M, "_resolve_wa_instance", _inst), \
             patch.object(M.httpx, "AsyncClient", _FakeClient):
            ok = await M.send_whatsapp_media_bytes(
                "59171234567", b"\x89PNG\r\n", "image/png", "foto.png", "Hola",
            )

        assert ok is True
        assert captured["url"] == "http://evo/message/sendMedia/apu"
        assert captured["json"]["mediatype"] == "image"
        assert captured["json"]["fileName"] == "foto.png"
        assert captured["json"]["mimetype"] == "image/png"
        assert captured["json"]["caption"] == "Hola"
        # La base64 debe decodificar al original
        import base64
        assert base64.b64decode(captured["json"]["media"]) == b"\x89PNG\r\n"

    async def test_returns_false_on_non_2xx(self):
        from app.services import messaging as M

        class _FakeResp:
            status_code = 500
            text = "boom"

        class _FakeClient:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **kw):
                return _FakeResp()

        async def _inst(_):
            return {"url": "http://evo", "instance_name": "apu", "api_key": "k"}

        with patch.object(M, "_resolve_wa_instance", _inst), \
             patch.object(M.httpx, "AsyncClient", _FakeClient):
            ok = await M.send_whatsapp_media_bytes(
                "59171234567", b"x", "application/pdf", "doc.pdf",
            )
        assert ok is False

    async def test_returns_false_when_no_instance(self):
        from app.services import messaging as M

        async def _inst(_):
            return None

        with patch.object(M, "_resolve_wa_instance", _inst):
            ok = await M.send_whatsapp_media_bytes(
                "59171234567", b"x", "image/png", "f.png",
            )
        assert ok is False


@pytest.fixture
def mock_send_media():
    """Mock send_whatsapp_media_bytes a nivel del módulo messaging."""
    with patch(
        "app.services.messaging.send_whatsapp_media_bytes",
        new=AsyncMock(return_value=True),
    ) as m:
        yield m


class TestMirrorOperatorMediaToClient:
    async def test_blocked_without_phone(self, db, sample_session, mock_send_media):
        sample_session.client_phone = None
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()

        ok = await mirror_operator_media_to_client(
            db, sample_session, b"content", "image/png", "f.png", caption="hi",
        )
        assert ok is False
        mock_send_media.assert_not_called()

    async def test_blocked_when_window_closed(self, db, sample_session, mock_send_media):
        sample_session.last_client_msg_at = datetime.now(timezone.utc) - timedelta(hours=48)
        await db.commit()

        ok = await mirror_operator_media_to_client(
            db, sample_session, b"content", "image/png", "f.png",
        )
        assert ok is False
        mock_send_media.assert_not_called()

    async def test_blocked_on_empty_content(self, db, sample_session, mock_send_media):
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()

        ok = await mirror_operator_media_to_client(
            db, sample_session, b"", "image/png", "f.png",
        )
        assert ok is False
        mock_send_media.assert_not_called()

    async def test_success_sends_and_records(self, db, sample_session, mock_send_media):
        sample_session.state = "active"
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()

        ok = await mirror_operator_media_to_client(
            db, sample_session, b"\x89PNG", "image/png", "foto.png",
            caption="Mirá la foto", operator_ref="42",
        )
        assert ok is True
        mock_send_media.assert_called_once()
        call_args = mock_send_media.call_args
        # positional: phone, content, mime, filename, caption
        assert call_args[0][0] == "59171234567"
        assert call_args[0][1] == b"\x89PNG"
        assert call_args[0][2] == "image/png"
        assert call_args[0][3] == "foto.png"
        assert call_args[0][4] == "Mirá la foto"

        # Estado transita a operator_engaged
        await db.refresh(sample_session)
        assert sample_session.state == "operator_engaged"

        # Se persistió el Message outbound con media_type="image"
        from sqlalchemy import select
        from app.models.conversation import Message
        msgs = (await db.execute(
            select(Message).where(Message.session_id == sample_session.id).order_by(Message.id)
        )).scalars().all()
        assert len(msgs) == 1
        assert msgs[0].direction == "outbound"
        assert msgs[0].channel == "whatsapp"
        assert msgs[0].sender_type == "operator"
        assert msgs[0].sender_ref == "42"
        assert msgs[0].body == "Mirá la foto"
        assert msgs[0].media_type == "image"

    async def test_document_mime_maps_to_document(self, db, sample_session, mock_send_media):
        sample_session.state = "active"
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()

        ok = await mirror_operator_media_to_client(
            db, sample_session, b"%PDF-1.7", "application/pdf", "cot.pdf",
        )
        assert ok is True

        from sqlalchemy import select
        from app.models.conversation import Message
        msg = (await db.execute(
            select(Message).where(Message.session_id == sample_session.id)
        )).scalars().first()
        assert msg.media_type == "document"

    async def test_failure_does_not_record(self, db, sample_session):
        sample_session.state = "active"
        sample_session.last_client_msg_at = datetime.now(timezone.utc)
        await db.commit()

        with patch(
            "app.services.messaging.send_whatsapp_media_bytes",
            new=AsyncMock(return_value=False),
        ):
            ok = await mirror_operator_media_to_client(
                db, sample_session, b"x", "image/png", "f.png",
            )
        assert ok is False

        from sqlalchemy import select
        from app.models.conversation import Message
        msgs = (await db.execute(
            select(Message).where(Message.session_id == sample_session.id)
        )).scalars().all()
        assert len(msgs) == 0
