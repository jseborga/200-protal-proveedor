"""Servicio de mensajeria multicanal: WhatsApp (Evolution API), Telegram, Email.

Envio de RFQs a proveedores y recepcion de respuestas.
"""

import httpx
import aiosmtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from app.core.config import settings


# ── Telegram Batch Sessions (in-memory) ─────────────────────────
# chat_id → {description, started_at, items: [{type, file_id, filename, mime, caption, content}]}
_batch_sessions: dict[str, dict] = {}
_BATCH_TIMEOUT_MINUTES = 30
_BATCH_MAX_ITEMS = 20


# ── WhatsApp (Evolution API) — Multi-instance ─────────────────
async def _resolve_wa_instance(instance_id: str | None = None) -> dict | None:
    """Resolve Evolution API instance config.

    Priority: DB evolution_instances (by id or default) → .env single instance.
    Returns dict with keys: url, api_key, instance_name, label.
    """
    try:
        from app.core.database import async_session
        from app.models.system_setting import SystemSetting

        async with async_session() as db:
            setting = await db.get(SystemSetting, "integrations")
            cfg = setting.value if setting and setting.value else {}

        instances = cfg.get("evolution_instances", [])
        if instances:
            if instance_id:
                inst = next((i for i in instances if i.get("id") == instance_id), None)
            else:
                inst = next((i for i in instances if i.get("is_default")), None) or instances[0]
            if inst and inst.get("url") and inst.get("api_key"):
                return {
                    "url": inst["url"].rstrip("/"),
                    "api_key": inst["api_key"],
                    "instance_name": inst.get("instance_name", "default"),
                    "label": inst.get("label", ""),
                }

        # Fallback: single instance from DB integrations or .env
        wa_url = cfg.get("evolution_api_url") or settings.evolution_api_url
        wa_key = cfg.get("evolution_api_key") or settings.evolution_api_key
        wa_name = cfg.get("evolution_instance_name") or settings.evolution_instance_name
        if wa_url and wa_key:
            return {
                "url": wa_url.rstrip("/"),
                "api_key": wa_key,
                "instance_name": wa_name,
                "label": "default",
            }
    except Exception:
        pass

    # Last resort: raw .env
    if settings.evolution_api_url and settings.evolution_api_key:
        return {
            "url": settings.evolution_api_url.rstrip("/"),
            "api_key": settings.evolution_api_key,
            "instance_name": settings.evolution_instance_name,
            "label": "default",
        }
    return None


async def send_whatsapp(phone: str, message: str, *, instance_id: str | None = None) -> bool:
    """Send WhatsApp message via Evolution API."""
    inst = await _resolve_wa_instance(instance_id)
    if not inst:
        return False

    url = f"{inst['url']}/message/sendText/{inst['instance_name']}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                headers={
                    "apikey": inst["api_key"],
                    "Content-Type": "application/json",
                },
                json={
                    "number": _format_phone(phone),
                    "text": message,
                },
            )
        return resp.status_code == 201
    except httpx.HTTPError:
        return False


async def send_whatsapp_file(phone: str, file_url: str, caption: str, *, instance_id: str | None = None) -> bool:
    """Send file via WhatsApp."""
    inst = await _resolve_wa_instance(instance_id)
    if not inst:
        return False

    url = f"{inst['url']}/message/sendMedia/{inst['instance_name']}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                headers={
                    "apikey": inst["api_key"],
                    "Content-Type": "application/json",
                },
                json={
                    "number": _format_phone(phone),
                    "mediatype": "document",
                    "media": file_url,
                    "caption": caption,
                },
            )
        return resp.status_code == 201
    except httpx.HTTPError:
        return False


def _wa_mediatype_from_mime(mime: str | None) -> str:
    """Map a MIME type to Evolution's mediatype field (image|video|audio|document)."""
    if not mime:
        return "document"
    m = mime.lower()
    if m.startswith("image/"):
        return "image"
    if m.startswith("video/"):
        return "video"
    if m.startswith("audio/"):
        return "audio"
    return "document"


async def send_whatsapp_media_bytes(
    phone: str,
    content: bytes,
    mime: str,
    filename: str,
    caption: str = "",
    *,
    instance_id: str | None = None,
) -> bool:
    """Send media bytes via WhatsApp using Evolution's base64 variant of sendMedia.

    Evolution API v2 accepts base64-encoded payload in the same /message/sendMedia
    endpoint by passing the media field as a base64 string (no data URI prefix).
    """
    import base64 as _b64

    inst = await _resolve_wa_instance(instance_id)
    if not inst:
        return False

    mediatype = _wa_mediatype_from_mime(mime)
    url = f"{inst['url']}/message/sendMedia/{inst['instance_name']}"
    payload = {
        "number": _format_phone(phone),
        "mediatype": mediatype,
        "media": _b64.b64encode(content).decode("ascii"),
        "fileName": filename or "archivo",
        "mimetype": mime or "application/octet-stream",
    }
    if caption:
        payload["caption"] = caption[:1024]

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url,
                headers={
                    "apikey": inst["api_key"],
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code in (200, 201):
            return True
        print(f"[WA] sendMedia(bytes) failed: {resp.status_code} {resp.text[:200]}")
        return False
    except httpx.HTTPError as e:
        print(f"[WA] sendMedia(bytes) error: {e}")
        return False


def _format_phone(phone: str) -> str:
    """Ensure phone number has country code."""
    phone = phone.strip().replace(" ", "").replace("-", "").replace("+", "")
    if not phone.startswith("591") and len(phone) == 8:
        phone = "591" + phone  # Bolivia default
    return phone


async def get_whatsapp_media_from_evolution(
    msg: dict,
    *,
    instance_id: str | None = None,
) -> tuple[bytes, str, str] | None:
    """Decrypt & download a WhatsApp media message via Evolution API.

    Returns (content, mime, filename) or None on failure.
    Evolution v2 endpoint: POST /chat/getBase64FromMediaMessage/{instance}
    """
    import base64

    inst = await _resolve_wa_instance(instance_id)
    if not inst:
        return None

    url = f"{inst['url']}/chat/getBase64FromMediaMessage/{inst['instance_name']}"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url,
                headers={
                    "apikey": inst["api_key"],
                    "Content-Type": "application/json",
                },
                json={"message": msg, "convertToMp4": False},
            )
        if resp.status_code not in (200, 201):
            print(f"[WA] media fetch failed: {resp.status_code} {resp.text[:200]}")
            return None
        data = resp.json()
        b64 = data.get("base64") or data.get("data") or ""
        if not b64:
            return None
        content = base64.b64decode(b64)
        mime = data.get("mimetype") or "application/octet-stream"
        filename = data.get("fileName") or data.get("filename") or "archivo"
        return content, mime, filename
    except Exception as e:
        print(f"[WA] media fetch error: {e}")
        return None


# ── Telegram ────────────────────────────────────────────────────
async def _resolve_telegram_token() -> str | None:
    """Resolve Telegram bot token from DB or .env."""
    try:
        from app.core.database import async_session
        from app.models.system_setting import SystemSetting
        async with async_session() as db:
            setting = await db.get(SystemSetting, "integrations")
            cfg = setting.value if setting and setting.value else {}
        token = cfg.get("telegram_bot_token")
        if token:
            return token
    except Exception:
        pass
    return settings.telegram_bot_token or None


async def send_telegram(
    chat_id: str,
    message: str,
    buttons: list[list[dict]] | None = None,
    message_thread_id: int | None = None,
) -> bool:
    """Send Telegram message with optional inline keyboard buttons.

    buttons format: [[{"text": "Label", "callback_data": "cmd"}], ...]
    Each inner list is a row of buttons.

    message_thread_id: if set, the message is posted to that forum topic
    within the group (requires the group to have topics enabled).
    """
    token = await _resolve_telegram_token()
    if not token:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    if message_thread_id is not None:
        payload["message_thread_id"] = message_thread_id

    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


# ── Telegram forum topics (hub de conversaciones) ──────────────
async def _resolve_hub_group_id() -> str | None:
    """Resolve the operator group chat_id from system_setting.integrations."""
    try:
        from app.core.database import async_session
        from app.models.system_setting import SystemSetting
        async with async_session() as db:
            setting = await db.get(SystemSetting, "integrations")
            cfg = setting.value if setting and setting.value else {}
        gid = cfg.get("conversation_hub_group_id")
        if gid:
            return str(gid)
    except Exception:
        pass
    return None


async def create_telegram_topic(
    group_id: str,
    name: str,
    icon_color: int | None = None,
) -> int | None:
    """Create a forum topic in the operator group. Returns message_thread_id.

    The group must have topics enabled and the bot must be admin with
    manage_topics permission.

    icon_color: optional int (one of 7322096, 16766590, 13338331, 9367192,
    16749490, 16478047, 14307864). If not set, TG uses a random color.
    """
    token = await _resolve_telegram_token()
    if not token or not group_id:
        return None

    url = f"https://api.telegram.org/bot{token}/createForumTopic"
    payload: dict = {"chat_id": group_id, "name": name[:128]}
    if icon_color is not None:
        payload["icon_color"] = icon_color

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            print(f"[TG] createForumTopic failed: {resp.status_code} {resp.text[:200]}")
            return None
        data = resp.json()
        if not data.get("ok"):
            print(f"[TG] createForumTopic not ok: {data}")
            return None
        return data["result"]["message_thread_id"]
    except httpx.HTTPError as e:
        print(f"[TG] createForumTopic http error: {e}")
        return None


async def close_telegram_topic(group_id: str, message_thread_id: int) -> bool:
    """Close a forum topic (readonly). Use when a pedido is completed."""
    token = await _resolve_telegram_token()
    if not token or not group_id:
        return False
    url = f"https://api.telegram.org/bot{token}/closeForumTopic"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json={
                "chat_id": group_id,
                "message_thread_id": message_thread_id,
            })
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


async def send_telegram_photo_to_topic(
    group_id: str,
    message_thread_id: int,
    photo_url_or_file_id: str,
    caption: str = "",
) -> bool:
    """Send a photo into a forum topic (used for mirroring WA photos)."""
    token = await _resolve_telegram_token()
    if not token or not group_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json={
                "chat_id": group_id,
                "message_thread_id": message_thread_id,
                "photo": photo_url_or_file_id,
                "caption": caption[:1024],
                "parse_mode": "HTML",
            })
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


async def send_telegram_media_bytes_to_topic(
    group_id: str,
    message_thread_id: int,
    content: bytes,
    filename: str,
    mime: str,
    caption: str = "",
    *,
    kind: str = "document",
) -> bool:
    """Upload a media file (bytes) into a forum topic via multipart.

    kind: 'photo' (image/*), 'document' (anything), 'audio' (audio/*), 'video' (video/*).
    For 'photo', TG accepts jpg/png; other images fall back to 'document'.
    """
    token = await _resolve_telegram_token()
    if not token or not group_id:
        return False

    endpoint_by_kind = {
        "photo": "sendPhoto",
        "document": "sendDocument",
        "audio": "sendAudio",
        "video": "sendVideo",
    }
    field_by_kind = {
        "photo": "photo",
        "document": "document",
        "audio": "audio",
        "video": "video",
    }
    endpoint = endpoint_by_kind.get(kind, "sendDocument")
    field = field_by_kind.get(kind, "document")

    url = f"https://api.telegram.org/bot{token}/{endpoint}"
    data = {
        "chat_id": str(group_id),
        "message_thread_id": str(message_thread_id),
        "caption": (caption or "")[:1024],
        "parse_mode": "HTML",
    }
    files = {field: (filename or "archivo", content, mime or "application/octet-stream")}

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, data=data, files=files)
        if resp.status_code != 200:
            print(f"[TG] {endpoint} failed: {resp.status_code} {resp.text[:200]}")
            return False
        return True
    except httpx.HTTPError as e:
        print(f"[TG] {endpoint} http error: {e}")
        return False


async def _answer_callback(callback_query_id: str, text: str = "") -> bool:
    """Answer a Telegram callback query (dismiss the loading spinner)."""
    token = await _resolve_telegram_token()
    if not token:
        return False
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={
                "callback_query_id": callback_query_id,
                "text": text,
            })
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


async def _download_telegram_file(file_id: str) -> tuple[bytes, str] | None:
    """Download a file from Telegram by file_id. Returns (content, file_path) or None."""
    token = await _resolve_telegram_token()
    if not token:
        return None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: get file path
            resp = await client.get(f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}")
            data = resp.json()
            if not data.get("ok"):
                return None
            file_path = data["result"]["file_path"]

            # Step 2: download content
            file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
            resp2 = await client.get(file_url)
            if resp2.status_code != 200:
                return None
            return resp2.content, file_path
    except Exception as e:
        print(f"[TG] Download error: {e}")
        return None


# ── Email ───────────────────────────────────────────────────────
async def send_email(to: str, subject: str, body_html: str) -> bool:
    """Send email via SMTP."""
    if not settings.smtp_user or not settings.smtp_password:
        return False

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body_html, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            use_tls=settings.smtp_tls,
        )
        return True
    except Exception:
        return False


# ── RFQ dispatch ────────────────────────────────────────────────
async def send_rfq_to_suppliers(rfq, suppliers, channels: list[str]) -> int:
    """Send RFQ to all target suppliers via specified channels."""
    sent = 0
    message = _build_rfq_message(rfq)
    html_message = _build_rfq_html(rfq)

    for supplier in suppliers:
        success = False

        if "whatsapp" in channels and supplier.whatsapp:
            success = await send_whatsapp(supplier.whatsapp, message) or success

        if "telegram" in channels and supplier.telegram_chat_id:
            success = await send_telegram(supplier.telegram_chat_id, message) or success

        if "email" in channels and supplier.email:
            success = await send_email(
                supplier.email,
                f"Solicitud de Cotizacion: {rfq.title} ({rfq.reference})",
                html_message,
            ) or success

        if success:
            sent += 1

    return sent


def _build_rfq_message(rfq) -> str:
    """Build plain text RFQ message for WhatsApp/Telegram."""
    lines = [
        f"📋 *Solicitud de Cotizacion*",
        f"Ref: {rfq.reference}",
        f"Titulo: {rfq.title}",
    ]
    if rfq.description:
        lines.append(f"Descripcion: {rfq.description}")
    if rfq.deadline:
        lines.append(f"Fecha limite: {rfq.deadline.strftime('%d/%m/%Y')}")
    if rfq.region:
        lines.append(f"Region: {rfq.region}")

    lines.append("\n*Items solicitados:*")
    for item in rfq.items:
        price_ref = f" (ref: {item.ref_price} {rfq.currency})" if item.ref_price else ""
        lines.append(f"• {item.name} — {item.quantity} {item.uom or 'und'}{price_ref}")

    lines.append(f"\nResponda a este mensaje con su cotizacion o ingrese al portal: {settings.app_url}")
    return "\n".join(lines)


def _build_rfq_html(rfq) -> str:
    """Build HTML RFQ message for email."""
    items_html = ""
    for item in rfq.items:
        price_ref = f"<small>(ref: {item.ref_price} {rfq.currency})</small>" if item.ref_price else ""
        items_html += f"<tr><td>{item.name}</td><td>{item.quantity}</td><td>{item.uom or 'und'}</td><td>{price_ref}</td></tr>"

    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px;">
        <h2>Solicitud de Cotizacion</h2>
        <p><strong>Ref:</strong> {rfq.reference}</p>
        <p><strong>Titulo:</strong> {rfq.title}</p>
        {"<p>" + rfq.description + "</p>" if rfq.description else ""}
        {"<p><strong>Fecha limite:</strong> " + rfq.deadline.strftime('%d/%m/%Y') + "</p>" if rfq.deadline else ""}
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
            <thead style="background: #f0f0f0;">
                <tr><th>Item</th><th>Cantidad</th><th>Unidad</th><th>Ref.</th></tr>
            </thead>
            <tbody>{items_html}</tbody>
        </table>
        <p style="margin-top: 20px;">
            <a href="{settings.app_url}" style="background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">
                Enviar Cotizacion
            </a>
        </p>
    </div>
    """


# ── Authorized users check ─────────────────────────────────────
async def _is_authorized_bot_user(db, channel: str, user_id: str) -> bool:
    """Verifica si el user_id esta autorizado para usar el bot AI."""
    from app.models.system_setting import SystemSetting
    setting = await db.get(SystemSetting, "bot_authorized_users")
    if not setting or not setting.value:
        print(f"[Auth] No bot_authorized_users setting found — rejecting {channel}:{user_id}")
        return False

    authorized = setting.value.get(channel, [])
    if not authorized:
        print(f"[Auth] No authorized users for channel '{channel}' — rejecting {user_id}")
        return False

    # Ensure all values are strings for comparison
    authorized_str = [str(a).strip() for a in authorized]
    user_id_str = str(user_id).strip()

    # Support both exact match and prefix match (for phone numbers)
    is_auth = any(
        user_id_str == a or user_id_str.endswith(a) or a.endswith(user_id_str)
        for a in authorized_str
    )
    if not is_auth:
        print(f"[Auth] {channel}:{user_id} not in authorized list: {authorized_str}")
    return is_auth


# ── Webhook handlers ───────────────────────────────────────────
async def handle_whatsapp_message(db, msg: dict):
    """Process incoming WhatsApp message.

    Ruteo:
    1) Si hay una ConversationSession activa para este phone → hub de
       conversaciones (mirror a TG topic + autoreply según estado).
    2) Si no hay sesión activa → fallback al bot AI (comportamiento antiguo)
       si el número está en la whitelist de bot_authorized_users.
    """
    remote_jid = msg.get("key", {}).get("remoteJid", "")
    phone = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid
    ext_id = msg.get("key", {}).get("id") or None

    # Extract text from any of the WhatsApp message shapes
    m = msg.get("message", {}) or {}
    text = (
        m.get("conversation")
        or m.get("extendedTextMessage", {}).get("text")
        or m.get("imageMessage", {}).get("caption")
        or m.get("documentMessage", {}).get("caption")
        or ""
    )
    media_note: str | None = None
    media_kind: str | None = None  # image|document|audio|video — used to decide whether to fetch bytes
    if m.get("imageMessage"):
        media_note = "imagen"
        media_kind = "image"
    elif m.get("documentMessage"):
        media_note = "documento"
        media_kind = "document"
    elif m.get("audioMessage"):
        media_note = "audio"
        media_kind = "audio"
    elif m.get("videoMessage"):
        media_note = "video"
        media_kind = "video"

    if not text and not media_note:
        return

    print(f"[WA] {phone}: [{media_note or 'text'}] {text[:120]}")

    # ── Conversation hub: if there's an active session for this phone ──
    try:
        from app.services.conversation_hub import (
            find_active_session_for_client, record_message,
            mirror_client_to_topic, bot_autoreply,
        )
        session = await find_active_session_for_client(db, phone)
    except Exception as e:
        print(f"[WA] hub lookup error: {e}")
        session = None

    if session is not None:
        try:
            # First inbound? advance state from waiting_first_contact → active
            if session.state == "waiting_first_contact":
                session.state = "active"

            # Log the inbound message
            await record_message(
                db, session,
                direction="inbound", channel="whatsapp",
                sender_type="client", sender_ref=phone,
                body=text or None, media_type=media_note,
                ext_message_id=ext_id,
            )

            # If media, try to fetch bytes from Evolution and relay to TG topic
            media_bytes: bytes | None = None
            media_mime: str | None = None
            media_filename: str | None = None
            if media_kind:
                fetched = await get_whatsapp_media_from_evolution(msg)
                if fetched:
                    media_bytes, media_mime, media_filename = fetched

            # Mirror to the operator TG topic
            await mirror_client_to_topic(
                db, session, text=text, sender_ref=phone, media_note=media_note,
                media_bytes=media_bytes, media_mime=media_mime, media_filename=media_filename,
            )

            # 5.5: Web Push al operador asignado (si hay) por cada inbound
            if session.operator_id:
                try:
                    from app.services.webpush import send_push_to_user
                    preview = (text or media_note or "Nuevo mensaje")[:140]
                    await send_push_to_user(
                        db, session.operator_id,
                        {
                            "title": f"Inbox · {phone}",
                            "body": preview,
                            "url": f"/#inbox",
                            "session_id": session.id,
                        },
                    )
                except Exception as e:  # noqa: BLE001
                    print(f"[webpush] hub error: {e}")

            # Bot autoreply (if appropriate)
            reply = await bot_autoreply(db, session, text or "")
            if reply:
                # WA uses plain text — strip simple HTML tags for readability
                clean_reply = reply.replace("<b>", "*").replace("</b>", "*").replace("<i>", "_").replace("</i>", "_")
                ok = await send_whatsapp(phone, clean_reply)
                if ok:
                    await record_message(
                        db, session,
                        direction="outbound", channel="whatsapp",
                        sender_type="bot", body=reply,
                    )
            await db.commit()
        except Exception as e:
            print(f"[WA] hub processing error: {e}")
            import traceback; traceback.print_exc()
            await db.rollback()
        return

    # ── Fallback: legacy AI bot flow (for authorized operators/admins) ──
    if not await _is_authorized_bot_user(db, "whatsapp", phone):
        return  # Silently ignore unauthorized messages without a session

    if not text:
        return

    try:
        from app.services.agent_executor import execute_agent_message, resolve_agent_config
        result = await resolve_agent_config(db, "communicator")
        if result is None or result[0] is None:
            await send_whatsapp(phone, "Bot AI no configurado. Configura un proveedor de IA en el admin.")
            return

        ai_config, agent_prompt = result
        response = await execute_agent_message(db, text, ai_config, agent_prompt)
        if response:
            await send_whatsapp(phone, response)
    except Exception as e:
        print(f"[WA] Agent error: {e}")
        await send_whatsapp(phone, f"Error procesando tu mensaje. Intenta de nuevo.")


async def _try_handle_operator_topic_reply(
    db,
    chat_id: str,
    message_thread_id: int,
    from_user_id: str,
    username: str,
    text: str,
    has_photo: bool,
    has_document: bool,
    msg: dict,
    ext_msg_id: str | None,
) -> bool:
    """Handle a message in a conversation-hub topic. Returns True if consumed."""
    from app.services.conversation_hub import (
        find_session_by_topic, mirror_operator_to_client, record_message,
        close_session_for_pedido,
    )
    from app.models.user import User
    from sqlalchemy import select

    # Is this the configured operator group?
    hub_group = await _resolve_hub_group_id()
    if not hub_group or str(hub_group) != str(chat_id):
        return False

    session = await find_session_by_topic(db, hub_group, message_thread_id)
    if session is None:
        return False

    # Verify sender is a registered cotizador
    user_stmt = select(User).where(User.telegram_user_id == from_user_id).limit(1)
    operator = (await db.execute(user_stmt)).scalar_one_or_none()
    if operator is None:
        await send_telegram(
            chat_id,
            f"⚠️ @{username} no está registrado como cotizador (tg_user_id: <code>{from_user_id}</code>). Pedile al admin que te registre.",
            message_thread_id=message_thread_id,
        )
        return True

    # ── Topic commands ─────────────────────────────────────────
    cmd = (text or "").strip().lower()
    if cmd in ("/cerrar", "/close"):
        try:
            from app.services.pedido import complete_pedido
            from app.models.pedido import Pedido
            pedido = await db.get(Pedido, session.pedido_id)
            if pedido and pedido.state != "completed":
                await complete_pedido(db, pedido)
            await close_session_for_pedido(db, session.pedido_id)
            await db.commit()
            await send_telegram(
                chat_id,
                f"✅ Pedido <b>#{session.pedido_id}</b> cerrado por @{username or operator.full_name}.",
                message_thread_id=message_thread_id,
            )
        except Exception as e:
            print(f"[TG] /cerrar error: {e}")
            import traceback; traceback.print_exc()
            await db.rollback()
            await send_telegram(
                chat_id,
                "⚠️ No se pudo cerrar el pedido. Revisa los logs.",
                message_thread_id=message_thread_id,
            )
        return True

    if cmd in ("/ayuda", "/help"):
        await send_telegram(
            chat_id,
            (
                "<b>Comandos del topic</b>\n"
                "<code>/cerrar</code> — marcar el pedido completado y cerrar el topic\n"
                "<code>/ayuda</code> — mostrar esta ayuda\n\n"
                "Cualquier otro mensaje se reenvía al cliente por WhatsApp."
            ),
            message_thread_id=message_thread_id,
        )
        return True

    try:
        if text and not (has_photo or has_document):
            # Plain text → relay to client WA
            ok = await mirror_operator_to_client(
                db, session, text, operator_ref=from_user_id,
            )
            if not ok:
                await send_telegram(
                    chat_id,
                    "⚠️ No pude enviar al cliente (ventana 24h cerrada o WA no configurado).",
                    message_thread_id=message_thread_id,
                )
        elif has_photo or has_document:
            # Fase 1.5: descargar de TG y reenviar a WA del cliente via
            # Evolution sendMedia (base64). Si falla, caer al aviso de Fase 1.
            from app.services.conversation_hub import mirror_operator_media_to_client

            file_id = None
            filename = "archivo"
            mime = "application/octet-stream"
            if has_photo:
                photos = msg.get("photo") or []
                if photos:
                    file_id = photos[-1].get("file_id")
                    filename = "foto.jpg"
                    mime = "image/jpeg"
            elif has_document:
                doc = msg.get("document") or {}
                file_id = doc.get("file_id")
                filename = doc.get("file_name") or "documento"
                mime = doc.get("mime_type") or "application/octet-stream"

            relayed = False
            if file_id:
                fetched = await _download_telegram_file(file_id)
                if fetched:
                    content, _ = fetched
                    relayed = await mirror_operator_media_to_client(
                        db, session, content, mime, filename,
                        caption=text or None,
                        operator_ref=from_user_id,
                    )
                else:
                    print(f"[TG→WA] no se pudo descargar file_id={file_id}")

            if relayed:
                # Log inbound TG event para trazabilidad; el outbound ya lo
                # escribió mirror_operator_media_to_client.
                await record_message(
                    db, session,
                    direction="inbound", channel="telegram",
                    sender_type="operator", sender_ref=from_user_id,
                    body=text or None,
                    media_type="photo" if has_photo else "document",
                    ext_message_id=ext_msg_id,
                )
            else:
                # Fallback Fase 1: avisar al cliente y dejar constancia.
                kind = "una foto" if has_photo else "un documento"
                caption_line = f"\nNota del cotizador: {text}" if text else ""
                client_msg = (
                    f"El equipo te envió {kind} sobre tu pedido {session.pedido_id}. "
                    f"Abrí el portal para verlo.{caption_line}"
                )
                await mirror_operator_to_client(
                    db, session, client_msg, operator_ref=from_user_id,
                )
                await record_message(
                    db, session,
                    direction="inbound", channel="telegram",
                    sender_type="operator", sender_ref=from_user_id,
                    body=text or None,
                    media_type="photo" if has_photo else "document",
                    ext_message_id=ext_msg_id,
                )
                await send_telegram(
                    chat_id,
                    "⚠️ No pude reenviar el archivo al cliente por WhatsApp (ventana 24h cerrada, WA sin configurar o falla de Evolution). Se notificó con texto.",
                    message_thread_id=message_thread_id,
                )

        await db.commit()
    except Exception as e:
        print(f"[TG] operator relay error: {e}")
        import traceback; traceback.print_exc()
        await db.rollback()

    return True


async def handle_telegram_message(db, msg: dict):
    """Process incoming Telegram message — text, photo, or document."""
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = msg.get("text", "") or msg.get("caption", "") or ""
    username = msg.get("from", {}).get("username", "")
    from_user_id = str(msg.get("from", {}).get("id", ""))
    message_thread_id = msg.get("message_thread_id")
    ext_msg_id = msg.get("message_id")

    # Detect media
    has_photo = bool(msg.get("photo"))
    has_document = bool(msg.get("document"))
    has_media = has_photo or has_document

    if not text and not has_media:
        return

    media_label = "foto" if has_photo else ("documento" if has_document else "texto")
    print(f"[TG] {chat_id} (@{username}): [{media_label}] thread={message_thread_id} {text[:80]}")

    # ── Conversation hub: operator reply inside a topic ─────────
    # If message is inside a forum topic belonging to a ConversationSession,
    # forward the operator's text to the client's WA.
    if message_thread_id is not None:
        handled = await _try_handle_operator_topic_reply(
            db, chat_id, message_thread_id,
            from_user_id, username, text,
            has_photo, has_document, msg,
            str(ext_msg_id) if ext_msg_id else None,
        )
        if handled:
            return

    # /start, /chatid, /help — always respond (no auth needed)
    if text.strip() in ("/start", "/chatid", "/help"):
        await send_telegram(chat_id, (
            "Hola! Soy el asistente de APU Marketplace.\n\n"
            f"Tu Chat ID: <code>{chat_id}</code>\n"
            "(Comparte este ID con el admin para autorizar tu acceso)\n\n"
            "<b>Envio directo</b> — envia 1 foto/PDF y se procesa al instante\n\n"
            "<b>Modo lote</b> — acumula varios archivos y procesa juntos\n\n"
            "<b>Comandos:</b>\n"
            "/lote [desc] — iniciar lote\n"
            "/procesar — procesar lote\n"
            "/diagnostico — probar IA\n"
            "/help — ver esta ayuda"
        ), buttons=[
            [
                {"text": "Iniciar Lote", "callback_data": "cmd_lote"},
                {"text": "Diagnostico IA", "callback_data": "cmd_diagnostico"},
            ],
            [
                {"text": "Estadisticas", "callback_data": "cmd_stats"},
                {"text": "Buscar Producto", "callback_data": "cmd_buscar"},
            ],
        ])
        return

    # Authorization check
    try:
        authorized = await _is_authorized_bot_user(db, "telegram", chat_id)
    except Exception as e:
        print(f"[TG] Auth check error for {chat_id}: {e}")
        authorized = False

    if not authorized:
        print(f"[TG] Unauthorized: chat_id={chat_id} @{username}")
        await send_telegram(
            chat_id,
            f"No estas autorizado para usar este bot.\n\n"
            f"Tu Chat ID: <code>{chat_id}</code>\n"
            f"Envia este ID al administrador para que te autorice en el panel."
        )
        return

    # ── Batch commands ──────────────────────────────────────────
    cmd = text.strip().split()[0].lower() if text.strip() else ""

    # Clean expired sessions
    _cleanup_expired_batches()

    if cmd == "/diagnostico":
        await _run_diagnostics(db, chat_id)
        return

    if cmd == "/lote":
        desc = text.strip()[len("/lote"):].strip()
        _batch_sessions[chat_id] = {
            "description": desc,
            "started_at": datetime.utcnow(),
            "items": [],
        }
        msg_text = "Lote iniciado."
        if desc:
            msg_text += f"\nDescripcion: <b>{desc}</b>"
        msg_text += (
            f"\n\nEnvia fotos, PDFs, Excel o texto (max {_BATCH_MAX_ITEMS})."
            "\nCada mensaje se acumula en el lote."
            "\n\nComandos:"
            "\n/procesar — procesar todo el lote"
            "\n/estado — ver que hay acumulado"
            "\n/cancelar — descartar el lote"
        )
        await send_telegram(chat_id, msg_text)
        return

    if cmd == "/cancelar":
        if chat_id in _batch_sessions:
            count = len(_batch_sessions[chat_id]["items"])
            del _batch_sessions[chat_id]
            await send_telegram(chat_id, f"Lote cancelado ({count} items descartados).")
        else:
            await send_telegram(chat_id, "No hay lote activo.")
        return

    if cmd == "/estado":
        if chat_id in _batch_sessions:
            session = _batch_sessions[chat_id]
            await send_telegram(chat_id, _build_batch_status(session))
        else:
            await send_telegram(chat_id, "No hay lote activo. Usa /lote para iniciar uno.")
        return

    if cmd == "/procesar":
        if chat_id not in _batch_sessions:
            await send_telegram(chat_id, "No hay lote activo. Usa /lote para iniciar uno.")
            return
        session = _batch_sessions.pop(chat_id)
        if not session["items"]:
            await send_telegram(chat_id, "El lote esta vacio. Nada que procesar.")
            return
        await _process_batch(db, chat_id, session)
        return

    # ── If batch mode is active, collect instead of processing ──
    if chat_id in _batch_sessions:
        session = _batch_sessions[chat_id]
        if len(session["items"]) >= _BATCH_MAX_ITEMS:
            await send_telegram(chat_id, f"Lote lleno ({_BATCH_MAX_ITEMS} items). Usa /procesar o /cancelar.")
            return

        item_added = False
        if has_photo:
            photos = msg.get("photo", [])
            file_id = photos[-1]["file_id"]
            session["items"].append({
                "type": "photo", "file_id": file_id,
                "filename": "foto.jpg", "mime": "image/jpeg",
                "caption": text,
            })
            item_added = True
        elif has_document:
            doc = msg.get("document", {})
            session["items"].append({
                "type": "document", "file_id": doc["file_id"],
                "filename": doc.get("file_name", "documento"),
                "mime": doc.get("mime_type", ""),
                "caption": text,
            })
            item_added = True
        elif text:
            session["items"].append({"type": "text", "content": text})
            item_added = True

        if item_added:
            n = len(session["items"])
            photos_n = sum(1 for i in session["items"] if i["type"] == "photo")
            docs_n = sum(1 for i in session["items"] if i["type"] == "document")
            texts_n = sum(1 for i in session["items"] if i["type"] == "text")

            parts = []
            if photos_n:
                parts.append(f"{photos_n} foto{'s' if photos_n > 1 else ''}")
            if docs_n:
                parts.append(f"{docs_n} doc{'s' if docs_n > 1 else ''}")
            if texts_n:
                parts.append(f"{texts_n} nota{'s' if texts_n > 1 else ''}")

            await send_telegram(
                chat_id,
                f"Agregado al lote ({', '.join(parts)}).",
                buttons=[
                    [
                        {"text": "Procesar Lote", "callback_data": "cmd_procesar"},
                        {"text": "Ver Estado", "callback_data": "cmd_estado"},
                    ],
                    [{"text": "Cancelar", "callback_data": "cmd_cancelar"}],
                ],
            )
        return

    # ── Regular processing (no batch) ───────────────────────────

    # Resolve AI config
    try:
        from app.services.agent_executor import execute_agent_message, resolve_agent_config
        result = await resolve_agent_config(db, "communicator")
    except Exception as e:
        print(f"[TG] Error resolving AI config: {e}")
        await send_telegram(chat_id, "Error interno al configurar el bot. Contacta al administrador.")
        return

    if result is None or result[0] is None:
        print("[TG] No AI config found")
        await send_telegram(chat_id, "Bot AI no configurado. Configura un proveedor de IA en el panel de administracion.")
        return
    ai_config, agent_prompt = result

    # ── Photo or Document: send directly to Claude Code ─────────
    if has_media:
        await send_telegram(chat_id, f"Recibida {media_label}. Enviando a Claude Code...")

        try:
            from app.services.temp_files import save_media_for_routine
            from app.services.agent_executor import fire_routine

            # Get file_id and classify
            if has_photo:
                photos = msg["photo"]
                file_id = photos[-1]["file_id"]
                source_type = "photo"
                filename = "cotizacion.jpg"
            else:
                doc = msg["document"]
                file_id = doc["file_id"]
                filename = doc.get("file_name", "document")
                mime = doc.get("mime_type", "")
                if "pdf" in mime:
                    source_type = "pdf"
                elif "image" in mime:
                    source_type = "photo"
                elif "spreadsheet" in mime or "excel" in mime or filename.endswith((".xlsx", ".xls")):
                    source_type = "excel"
                else:
                    source_type = "photo"

            # Download from Telegram
            dl = await _download_telegram_file(file_id)
            if not dl:
                await send_telegram(chat_id, "No pude descargar el archivo. Intenta de nuevo.")
                return
            content, file_path = dl
            print(f"[TG] Downloaded {len(content)} bytes: {file_path}")

            # Save to temp storage (PDF pages get converted to images)
            saved = save_media_for_routine(content, filename, source_type)
            if not saved:
                await send_telegram(chat_id, "Error preparando el archivo.")
                return

            # User hint (caption text)
            user_hint = text.strip() if text.strip() else ""

            # Build routine task with image tokens
            routine_task = _build_routine_task_for_media(
                saved_files=saved,
                source_type=source_type,
                filename=filename,
                user_hint=user_hint,
                source="telegram",
                chat_id=chat_id,
            )

            routine_result = await fire_routine(db, routine_task)

            if routine_result.get("estado") == "iniciada":
                session_url = routine_result.get("url", "")
                type_label = "PDF" if source_type == "pdf" else ("Excel" if source_type == "excel" else "Foto")
                pages_info = f" ({len(saved)} paginas)" if source_type == "pdf" and len(saved) > 1 else ""

                if source_type == "excel":
                    action_desc = "leera el Excel, extraera los datos"
                elif source_type == "pdf":
                    action_desc = "analizara las imagenes del PDF, extraera los datos"
                else:
                    action_desc = "analizara la imagen, extraera los datos"

                reply = (
                    f"{type_label}{pages_info} enviado a Claude Code.\n"
                    f"Claude Code {action_desc} "
                    f"y registrara productos y precios automaticamente.\n"
                    f"Recibiras una confirmacion cuando termine."
                )
                if user_hint:
                    reply += f"\nNota: {user_hint}"
                if session_url:
                    reply += f"\n\nSesion: {session_url}"
                await send_telegram(chat_id, reply)
            else:
                routine_error = routine_result.get("error", "")
                print(f"[TG] Routine unavailable: {routine_error}")
                await send_telegram(
                    chat_id,
                    f"No se pudo delegar a Claude Code.\n"
                    f"Error: {routine_error[:150]}\n\n"
                    f"Verifica la configuracion de Routine en Admin > Integraciones.",
                )

        except Exception as e:
            print(f"[TG] Media processing error: {e}")
            import traceback
            traceback.print_exc()
            await send_telegram(chat_id, f"Error procesando la {media_label}: {str(e)[:100]}")
        return

    # ── Text only: route to AI agent ─────────────────────────────
    try:
        response = await execute_agent_message(db, text, ai_config, agent_prompt)
        if response:
            await send_telegram(chat_id, response)
    except Exception as e:
        print(f"[TG] Agent error: {e}")
        await send_telegram(chat_id, "Error procesando tu mensaje. Intenta de nuevo.")


# ── Routine task builder ──────────────────────────────────────

def _build_routine_task_for_media(
    saved_files: list[dict],
    source_type: str,
    filename: str,
    user_hint: str = "",
    source: str = "telegram",
    batch_description: str = "",
    chat_id: str = "",
) -> str:
    """Build the task text for Claude Code Routine with image tokens.

    Instructs Claude Code to use get_uploaded_image to see each image,
    extract data, register products/prices, and notify the user via Telegram.
    """
    image_tokens = [f for f in saved_files if f["media_type"].startswith("image/")]
    excel_tokens = [f for f in saved_files if "excel" in f["media_type"] or f["filename"].endswith((".xlsx", ".xls"))]

    parts = []
    parts.append(f"PROCESAR DOCUMENTO recibido por {source.upper()}.")
    if batch_description:
        parts.append(f"Descripcion del lote: {batch_description}")
    if chat_id:
        parts.append(f"TELEGRAM CHAT_ID: {chat_id}")
    parts.append("")

    # Image viewing instructions
    if image_tokens:
        parts.append(f"HAY {len(image_tokens)} IMAGEN(ES) PARA ANALIZAR.")
        parts.append("Para ver cada imagen, usa la herramienta get_uploaded_image con el token correspondiente:")
        parts.append("")
        for f in image_tokens:
            label = f"Pagina {f['page']}" if f["page"] > 0 else f["filename"]
            parts.append(f"  - Token: {f['token']}  ({label}, {f['size']} bytes)")
        parts.append("")
        parts.append("IMPORTANTE: Llama get_uploaded_image para CADA token. Veras la imagen y podras extraer los datos.")
        parts.append("")

    # Excel instructions
    if excel_tokens:
        parts.append(f"HAY {len(excel_tokens)} ARCHIVO(S) EXCEL.")
        parts.append("Para leer cada Excel, usa la herramienta get_uploaded_excel con el token:")
        parts.append("")
        for f in excel_tokens:
            parts.append(f"  - Token: {f['token']}  ({f['filename']}, {f['size']} bytes)")
        parts.append("")

    # User hint
    if user_hint:
        parts.append(f"NOTA DEL USUARIO: {user_hint}")
        parts.append("")

    # Instructions
    parts.append("INSTRUCCIONES:")
    parts.append("")
    parts.append("PASO 1 — VER EL DOCUMENTO:")
    parts.append("  Llama get_uploaded_image (o get_uploaded_excel) para ver el contenido completo.")
    parts.append("")
    parts.append("PASO 2 — ANALISIS CONTEXTUAL DEL DOCUMENTO:")
    parts.append("  Antes de registrar datos, analiza el contexto completo del documento:")
    parts.append("  a) TIPO DE DOCUMENTO: factura, cotizacion, proforma, lista de precios, nota de venta.")
    parts.append("     Esto afecta la confiabilidad del precio (factura > cotizacion > lista).")
    parts.append("  b) PROVEEDOR: nombre, NIT, telefono, direccion, ciudad, departamento.")
    parts.append("     Infiere la ESPECIALIDAD del proveedor por lo que vende:")
    parts.append("     - Si vende cemento, arena, grava → proveedor de agregados/cemento")
    parts.append("     - Si vende cables, tubos PVC → proveedor electrico/sanitario")
    parts.append("     - Si vende fierro, clavos, tornillos → ferreteria/acero")
    parts.append("     Actualiza las categories del proveedor con update_supplier si es necesario.")
    parts.append("  c) ITEMS: analiza el CONJUNTO de productos para entender el contexto:")
    parts.append("     - Si hay cemento + arena + grava → obra civil/estructura")
    parts.append("     - Si hay cables + tableros + interruptores → instalacion electrica")
    parts.append("     - Usa el contexto para desambiguar: 'tubo 1/2' con cables = tubo conduit electrico,")
    parts.append("       'tubo 1/2' con sanitarios = tubo PVC agua")
    parts.append("  d) PRECIOS: verifica que sean coherentes con el mercado boliviano (Bs).")
    parts.append("     Si un precio parece total en vez de unitario, divide por la cantidad.")
    parts.append("  e) UNIDADES: normaliza a abreviaturas estandar (bls, kg, m3, m2, ml, pza, und, lt, gl, m, rollo, varilla, tubo).")
    parts.append("     Infiere la unidad del contexto si no esta explicita.")
    parts.append("")
    parts.append("PASO 3 — PROVEEDOR:")
    parts.append("  Busca con list_suppliers si ya existe (por nombre o NIT).")
    parts.append("  Si existe: actualiza sus datos con update_supplier si hay info nueva (telefono, direccion, categories).")
    parts.append("  Si no existe: crealo con create_supplier incluyendo city, department, categories inferidas.")
    parts.append("")
    parts.append("PASO 4 — PRODUCTOS:")
    parts.append("  Para cada item, busca con list_products Y search_product_fuzzy si ya existe.")
    parts.append("  Considera variaciones: 'Cemento IP-30' = 'CEMENTO PORTLAND IP-30' = 'Cem. IP30'.")
    parts.append("  Clasifica usando el contexto del documento, no solo el nombre del item:")
    parts.append("  - Categorias: ferreteria, agregados, acero, electrico, sanitario, madera, cemento,")
    parts.append("    pintura, ceramica, herramientas, techos, plomeria, vidrios, prefabricados, seguridad.")
    parts.append("  Productos nuevos: crealos con create_products_bulk (nombre limpio y estandarizado,")
    parts.append("  unidad correcta, categoria por contexto, precio como ref_price).")
    parts.append("")
    parts.append("PASO 5 — PRECIOS:")
    parts.append(f"  Registra TODOS los precios con create_price_history_bulk (source: '{source}', observed_date: hoy).")
    parts.append("  Vincula proveedor-producto con link_supplier_product para cada item.")
    parts.append("")

    # Telegram notification instruction
    if chat_id:
        parts.append(f"PASO 6 — NOTIFICAR AL USUARIO (OBLIGATORIO):")
        parts.append(f"  Llama notify_telegram con chat_id='{chat_id}' y un mensaje resumen en HTML.")
        parts.append("  Incluye:")
        parts.append("  - Tipo de documento procesado")
        parts.append("  - Proveedor: nombre, si es nuevo o existente, especialidad detectada")
        parts.append("  - Productos: cuantos nuevos, cuantos existentes, categorias asignadas")
        parts.append("  - Precios: cuantos registrados")
        parts.append("  - Observaciones: precios inusuales, items no identificados, datos faltantes")
        parts.append("  Ejemplo:")
        parts.append("  '<b>Cotizacion procesada</b>")
        parts.append("  <b>Proveedor:</b> Ferreteria El Constructor (existente)")
        parts.append("  Especialidad: ferreteria, acero")
        parts.append("  <b>Productos:</b> 5 nuevos, 3 existentes")
        parts.append("  Categorias: acero(4), ferreteria(3), cemento(1)")
        parts.append("  <b>Precios:</b> 8 registrados")
        parts.append("  <b>Obs:</b> Precio de Fierro 12mm (85 Bs/varilla) parece alto vs promedio (72 Bs)'")
        parts.append("")
        parts.append("MANEJO DE ERRORES:")
        parts.append(f"  Si ocurre CUALQUIER error (token expirado, Excel no parseable, imagen ilegible,")
        parts.append(f"  error en MCP tools), SIEMPRE llama notify_telegram con chat_id='{chat_id}'")
        parts.append(f"  informando el problema. El usuario debe saber que paso. Ejemplo:")
        parts.append("  '<b>Error procesando documento</b>\\nNo se pudo leer el archivo Excel.\\n")
        parts.append("  El formato no es compatible. Intenta enviar una captura de pantalla.'")
    else:
        parts.append("PASO 6 — Reporta un resumen detallado de lo procesado.")

    return "\n".join(parts)


# ── Batch helpers ──────────────────────────────────────────────

def _cleanup_expired_batches():
    """Remove batch sessions older than timeout."""
    now = datetime.utcnow()
    expired = [
        cid for cid, s in _batch_sessions.items()
        if now - s["started_at"] > timedelta(minutes=_BATCH_TIMEOUT_MINUTES)
    ]
    for cid in expired:
        del _batch_sessions[cid]
        print(f"[TG-Batch] Expired session for {cid}")


def _build_batch_status(session: dict) -> str:
    """Build a status message for the current batch."""
    desc = session.get("description", "")
    items = session["items"]
    elapsed = datetime.utcnow() - session["started_at"]
    mins = int(elapsed.total_seconds() / 60)

    photos = [i for i in items if i["type"] == "photo"]
    docs = [i for i in items if i["type"] == "document"]
    texts = [i for i in items if i["type"] == "text"]

    lines = ["<b>Lote activo</b>"]
    if desc:
        lines.append(f"Descripcion: {desc}")
    lines.append(f"Tiempo: {mins} min (expira a los {_BATCH_TIMEOUT_MINUTES} min)")
    lines.append(f"\nContenido ({len(items)} items):")

    if photos:
        lines.append(f"  - {len(photos)} foto{'s' if len(photos) > 1 else ''}")
    if docs:
        for d in docs:
            lines.append(f"  - {d.get('filename', 'doc')}")
    if texts:
        for t in texts:
            preview = t["content"][:60] + ("..." if len(t["content"]) > 60 else "")
            lines.append(f'  - Nota: "{preview}"')

    lines.append("\n/procesar — procesar todo")
    lines.append("/cancelar — descartar")
    return "\n".join(lines)


async def _process_batch(db, chat_id: str, session: dict):
    """Process a completed batch: download all files, save to temp, delegate to Claude Code."""
    desc = session.get("description", "")
    items = session["items"]

    media_items = [i for i in items if i["type"] in ("photo", "document")]
    text_notes = [i["content"] for i in items if i["type"] == "text"]

    if not media_items and not text_notes:
        await send_telegram(chat_id, "Lote vacio.")
        return

    await send_telegram(
        chat_id,
        f"Procesando lote: {len(media_items)} archivo{'s' if len(media_items) != 1 else ''}"
        + (f", {len(text_notes)} nota{'s' if len(text_notes) != 1 else ''}" if text_notes else "")
        + "\nDescargando y enviando a Claude Code..."
    )

    from app.services.temp_files import save_media_for_routine
    from app.services.agent_executor import fire_routine

    # ── Download and save all media files ──────────────────────
    all_saved = []
    download_errors = []

    for idx, item in enumerate(media_items, 1):
        file_id = item["file_id"]
        filename = item.get("filename", "archivo")
        mime = item.get("mime_type", item.get("mime", ""))

        if item["type"] == "photo":
            source_type = "photo"
        elif "pdf" in mime:
            source_type = "pdf"
        elif "image" in mime:
            source_type = "photo"
        elif "spreadsheet" in mime or "excel" in mime or filename.endswith((".xlsx", ".xls")):
            source_type = "excel"
        else:
            source_type = "photo"

        dl = await _download_telegram_file(file_id)
        if not dl:
            download_errors.append(f"No pude descargar {filename}")
            continue
        content, file_path = dl
        print(f"[TG-Batch] Downloaded #{idx}: {len(content)} bytes ({file_path})")

        try:
            saved = save_media_for_routine(content, filename, source_type)
            all_saved.extend(saved)
        except Exception as e:
            print(f"[TG-Batch] Save error for #{idx}: {e}")
            download_errors.append(f"Error procesando {filename}: {str(e)[:80]}")

    if not all_saved:
        error_detail = "\n".join(f"- {e}" for e in download_errors) if download_errors else "Sin detalles"
        await send_telegram(chat_id, f"No se pudieron preparar los archivos.\n\n{error_detail}")
        return

    # ── Build user hint from notes ─────────────────────────────
    user_hint = ""
    if text_notes:
        user_hint = "; ".join(text_notes)
    if desc and not user_hint:
        user_hint = desc
    elif desc:
        user_hint = f"{desc}. {user_hint}"

    # ── Build and fire routine task ────────────────────────────
    routine_task = _build_routine_task_for_media(
        saved_files=all_saved,
        source_type="batch",
        filename=f"lote_{len(media_items)}_archivos",
        user_hint=user_hint,
        source="telegram_batch",
        batch_description=desc,
        chat_id=chat_id,
    )

    routine_result = await fire_routine(db, routine_task)

    images_n = sum(1 for f in all_saved if f["media_type"].startswith("image/"))
    excels_n = sum(1 for f in all_saved if "excel" in f["media_type"])

    if routine_result.get("estado") == "iniciada":
        session_url = routine_result.get("url", "")
        summary = (
            f"<b>Lote enviado a Claude Code</b>\n"
            + (f"Descripcion: {desc}\n" if desc else "")
            + f"Archivos: {len(media_items)} | Imagenes: {images_n}"
            + (f" | Excel: {excels_n}" if excels_n else "")
            + "\n\nClaude Code analizara cada imagen, extraera los datos "
            "y registrara productos y precios automaticamente."
        )
        if download_errors:
            summary += f"\n\nErrores de descarga: {len(download_errors)}"
        if session_url:
            summary += f"\n\nSesion: {session_url}"
        await send_telegram(chat_id, summary)
    else:
        routine_error = routine_result.get("error", "")
        print(f"[TG-Batch] Routine unavailable: {routine_error}")
        await send_telegram(
            chat_id,
            f"No se pudo delegar a Claude Code.\n"
            f"Error: {routine_error[:150]}\n\n"
            f"Verifica la configuracion de Routine en Admin > Integraciones.",
        )


# ── Callback handler (inline button clicks) ──────────────────

async def handle_telegram_callback(db, callback: dict):
    """Handle inline keyboard button presses."""
    callback_id = callback.get("id", "")
    chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
    data = callback.get("data", "")
    username = callback.get("from", {}).get("username", "")
    from_user_id = str(callback.get("from", {}).get("id", ""))
    message_thread_id = callback.get("message", {}).get("message_thread_id")

    print(f"[TG-CB] {chat_id} (@{username}): {data}")

    # Always acknowledge the callback to dismiss the loading spinner
    await _answer_callback(callback_id)

    if not chat_id:
        return

    # ── Conversation hub: claim pedido ──────────────────────────
    if data.startswith("cb_claim_pedido_"):
        try:
            pedido_id = int(data[len("cb_claim_pedido_"):])
        except ValueError:
            return
        from app.services.conversation_hub import claim_pedido
        claimed_user = await claim_pedido(db, pedido_id, from_user_id)
        await db.commit()
        if claimed_user is None:
            await send_telegram(
                chat_id,
                f"No se pudo tomar el pedido. Puede que otro operador lo haya tomado antes, o tu Telegram no está registrado como cotizador (tu ID: <code>{from_user_id}</code>).",
                message_thread_id=message_thread_id,
            )
        else:
            await send_telegram(
                chat_id,
                f"✅ Pedido tomado por <b>{claimed_user.full_name}</b> (@{username}).",
                message_thread_id=message_thread_id,
            )
        return

    # Authorization check (except for start/help)
    if data not in ("cmd_start", "cmd_help"):
        try:
            authorized = await _is_authorized_bot_user(db, "telegram", chat_id)
        except Exception:
            authorized = False
        if not authorized:
            await send_telegram(
                chat_id,
                f"No estas autorizado.\nTu Chat ID: <code>{chat_id}</code>"
            )
            return

    # Route callback commands
    if data == "cmd_lote":
        _cleanup_expired_batches()
        _batch_sessions[chat_id] = {
            "description": "",
            "started_at": datetime.utcnow(),
            "items": [],
        }
        await send_telegram(
            chat_id,
            f"Lote iniciado.\n\nEnvia fotos, PDFs, Excel o texto (max {_BATCH_MAX_ITEMS})."
            "\nCada mensaje se acumula en el lote.",
            buttons=[
                [{"text": "Cancelar", "callback_data": "cmd_cancelar"}],
            ],
        )

    elif data == "cmd_procesar":
        _cleanup_expired_batches()
        if chat_id not in _batch_sessions:
            await send_telegram(chat_id, "No hay lote activo.")
            return
        session = _batch_sessions.pop(chat_id)
        if not session["items"]:
            await send_telegram(chat_id, "El lote esta vacio.")
            return
        await _process_batch(db, chat_id, session)

    elif data == "cmd_estado":
        _cleanup_expired_batches()
        if chat_id in _batch_sessions:
            await send_telegram(chat_id, _build_batch_status(_batch_sessions[chat_id]))
        else:
            await send_telegram(chat_id, "No hay lote activo.")

    elif data == "cmd_cancelar":
        if chat_id in _batch_sessions:
            count = len(_batch_sessions[chat_id]["items"])
            del _batch_sessions[chat_id]
            await send_telegram(chat_id, f"Lote cancelado ({count} items descartados).")
        else:
            await send_telegram(chat_id, "No hay lote activo.")

    elif data == "cmd_diagnostico":
        await _run_diagnostics(db, chat_id)

    elif data == "cmd_stats":
        # Quick stats via agent
        try:
            from app.services.agent_executor import execute_agent_message, resolve_agent_config
            result = await resolve_agent_config(db, "communicator")
            if result and result[0]:
                ai_config, agent_prompt = result
                response = await execute_agent_message(db, "dame las estadisticas del sistema", ai_config, agent_prompt)
                if response:
                    await send_telegram(chat_id, response)
                    return
        except Exception as e:
            print(f"[TG-CB] Stats error: {e}")
        await send_telegram(chat_id, "No pude obtener estadisticas.")

    elif data == "cmd_buscar":
        await send_telegram(
            chat_id,
            "Escribe el nombre del producto que buscas.\nEjemplo: <i>cemento portland</i>"
        )

    elif data == "cmd_help":
        # Re-trigger /start
        await send_telegram(chat_id, (
            "<b>Comandos disponibles:</b>\n\n"
            "/lote [desc] — iniciar lote\n"
            "/procesar — procesar lote\n"
            "/estado — ver lote actual\n"
            "/cancelar — cancelar lote\n"
            "/diagnostico — probar IA\n"
            "/chatid — ver tu Chat ID\n"
            "/help — esta ayuda"
        ), buttons=[
            [
                {"text": "Iniciar Lote", "callback_data": "cmd_lote"},
                {"text": "Diagnostico IA", "callback_data": "cmd_diagnostico"},
            ],
            [
                {"text": "Estadisticas", "callback_data": "cmd_stats"},
                {"text": "Buscar Producto", "callback_data": "cmd_buscar"},
            ],
        ])


# ── Diagnostics ───────────────────────────────────────────────

async def _run_diagnostics(db, chat_id: str):
    """Run AI diagnostic checks and report to user."""
    await send_telegram(chat_id, "Ejecutando diagnostico...")

    lines = ["<b>Diagnostico del Bot AI</b>\n"]

    # 1. Check AI configs
    from app.services.ai_extract import resolve_all_ai_configs
    configs = await resolve_all_ai_configs()
    if not configs:
        lines.append("AI Config: NO CONFIGURADO")
        lines.append("→ Configura un proveedor de IA en Admin > IA")
        await send_telegram(chat_id, "\n".join(lines))
        return

    for i, c in enumerate(configs, 1):
        priority = "Principal" if i == 1 else f"Fallback {i-1}"
        lines.append(f"\n<b>{priority}:</b> {c['provider']} / {c['model']}")
        lines.append(f"  Formato: {c['api_format']}")
        lines.append(f"  Key: {c['api_key'][:8]}...{c['api_key'][-4:]}")

        # 2. Test API call
        try:
            import httpx
            if c["api_format"] == "google":
                base = c["base_url"].rstrip("/")
                url = f"{base}/models/{c['model']}:generateContent?key={c['api_key']}"
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(
                        url,
                        headers={"Content-Type": "application/json"},
                        json={
                            "contents": [{"parts": [{"text": "Responde SOLO: ok"}]}],
                            "generationConfig": {"maxOutputTokens": 10},
                        },
                    )
                if resp.status_code == 200:
                    data = resp.json()
                    text = ""
                    for cand in data.get("candidates", []):
                        for part in cand.get("content", {}).get("parts", []):
                            text += part.get("text", "")
                    lines.append(f"  Test: OK — respuesta: \"{text.strip()[:50]}\"")
                else:
                    lines.append(f"  Test: ERROR {resp.status_code}")
                    lines.append(f"  {resp.text[:100]}")

            elif c["api_format"] == "anthropic":
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(
                        c["base_url"],
                        headers={
                            "x-api-key": c["api_key"],
                            "anthropic-version": "2023-06-01",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": c["model"],
                            "messages": [{"role": "user", "content": "Responde SOLO: ok"}],
                            "max_tokens": 10,
                        },
                    )
                if resp.status_code == 200:
                    data = resp.json()
                    text = data.get("content", [{}])[0].get("text", "")
                    lines.append(f"  Test: OK — respuesta: \"{text.strip()[:50]}\"")
                else:
                    lines.append(f"  Test: ERROR {resp.status_code}")
                    lines.append(f"  {resp.text[:100]}")

            else:  # openai / openrouter
                base_url = c["base_url"].rstrip("/")
                endpoint = f"{base_url}/chat/completions" if not base_url.endswith("/chat/completions") else base_url
                headers = {
                    "Authorization": f"Bearer {c['api_key']}",
                    "Content-Type": "application/json",
                }
                if c["api_format"] == "openrouter":
                    headers["HTTP-Referer"] = "https://apu-marketplace.com"
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(
                        endpoint,
                        headers=headers,
                        json={
                            "model": c["model"],
                            "messages": [{"role": "user", "content": "Responde SOLO: ok"}],
                            "max_tokens": 10,
                        },
                    )
                if resp.status_code == 200:
                    data = resp.json()
                    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    lines.append(f"  Test: OK — respuesta: \"{text.strip()[:50]}\"")
                else:
                    lines.append(f"  Test: ERROR {resp.status_code}")
                    lines.append(f"  {resp.text[:100]}")

        except Exception as e:
            lines.append(f"  Test: EXCEPCION — {str(e)[:100]}")

    # 3. Check Routine config
    from app.models.system_setting import SystemSetting
    routine_setting = await db.get(SystemSetting, "routine_config")
    if routine_setting and routine_setting.value and routine_setting.value.get("token"):
        lines.append(f"\nClaude Routine: Configurada (ID: {routine_setting.value.get('routine_id', '?')[:20]})")
    else:
        lines.append("\nClaude Routine: No configurada")

    # 4. Check bot auth
    bot_setting = await db.get(SystemSetting, "bot_authorized_users")
    if bot_setting and bot_setting.value:
        tg_list = bot_setting.value.get("telegram", [])
        lines.append(f"Usuarios TG autorizados: {len(tg_list)}")
        if chat_id in [str(x) for x in tg_list]:
            lines.append(f"Tu acceso: AUTORIZADO")
        else:
            lines.append(f"Tu acceso: NO (tu ID: {chat_id})")
    else:
        lines.append("Usuarios autorizados: No configurado")

    await send_telegram(chat_id, "\n".join(lines))
