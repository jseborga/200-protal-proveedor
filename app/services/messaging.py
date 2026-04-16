"""Servicio de mensajeria multicanal: WhatsApp (Evolution API), Telegram, Email.

Envio de RFQs a proveedores y recepcion de respuestas.
"""

import httpx
import aiosmtplib
from email.message import EmailMessage

from app.core.config import settings


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


def _format_phone(phone: str) -> str:
    """Ensure phone number has country code."""
    phone = phone.strip().replace(" ", "").replace("-", "").replace("+", "")
    if not phone.startswith("591") and len(phone) == 8:
        phone = "591" + phone  # Bolivia default
    return phone


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


async def send_telegram(chat_id: str, message: str) -> bool:
    """Send Telegram message."""
    token = await _resolve_telegram_token()
    if not token:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            )
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
        return False

    authorized = setting.value.get(channel, [])
    # Support both exact match and prefix match (for phone numbers)
    return any(user_id == a or user_id.endswith(a) or a.endswith(user_id) for a in authorized)


# ── Webhook handlers ───────────────────────────────────────────
async def handle_whatsapp_message(db, msg: dict):
    """Process incoming WhatsApp message — if authorized, route to AI agent."""
    remote_jid = msg.get("key", {}).get("remoteJid", "")
    phone = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid
    text = msg.get("message", {}).get("conversation") or msg.get("message", {}).get("extendedTextMessage", {}).get("text", "")

    if not text:
        return

    print(f"[WA] {phone}: {text}")

    # Check if user is authorized for bot
    if not await _is_authorized_bot_user(db, "whatsapp", phone):
        return  # Silently ignore unauthorized messages

    # Route to AI agent
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


async def handle_telegram_message(db, msg: dict):
    """Process incoming Telegram message — text, photo, or document."""
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = msg.get("text", "") or msg.get("caption", "") or ""
    username = msg.get("from", {}).get("username", "")

    # Detect media
    has_photo = bool(msg.get("photo"))
    has_document = bool(msg.get("document"))
    has_media = has_photo or has_document

    if not text and not has_media:
        return

    media_label = "foto" if has_photo else ("documento" if has_document else "texto")
    print(f"[TG] {chat_id} (@{username}): [{media_label}] {text[:80]}")

    # /start command
    if text.strip() == "/start":
        await send_telegram(chat_id, (
            "Hola! Soy el asistente de APU Marketplace.\n\n"
            "Preguntame sobre productos, precios, proveedores o pideme ejecutar tareas.\n\n"
            "Tambien puedes enviarme una FOTO o PDF de una cotizacion y la proceso automaticamente "
            "(extraigo proveedor, items y precios).\n\n"
            "Ejemplos:\n"
            "- cuantos productos hay?\n"
            "- busca cemento en Santa Cruz\n"
            "- precios de fierro corrugado\n"
            "- [envia una foto de cotizacion]"
        ))
        return

    # Authorization check
    if not await _is_authorized_bot_user(db, "telegram", chat_id):
        await send_telegram(chat_id, "No estas autorizado para usar este bot. Contacta al administrador.")
        return

    # Resolve AI config
    from app.services.agent_executor import execute_agent_message, resolve_agent_config
    result = await resolve_agent_config(db, "communicator")
    if result is None or result[0] is None:
        await send_telegram(chat_id, "Bot AI no configurado. Configura un proveedor de IA en el panel de administracion.")
        return
    ai_config, agent_prompt = result

    # ── Photo or Document: extract + process ────────────────────
    if has_media:
        await send_telegram(chat_id, f"Recibida {media_label}. Procesando...")

        try:
            # Get file_id
            if has_photo:
                # Telegram sends multiple sizes, take the largest
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
                    source_type = "photo"  # try as image

            # Download from Telegram
            dl = await _download_telegram_file(file_id)
            if not dl:
                await send_telegram(chat_id, "No pude descargar el archivo. Intenta de nuevo.")
                return
            content, file_path = dl
            print(f"[TG] Downloaded {len(content)} bytes: {file_path}")

            # Extract with AI
            from app.services.ai_extract import extract_quotation_data
            extraction = await extract_quotation_data(content, filename, source_type)

            if not extraction or not extraction.get("lines"):
                await send_telegram(chat_id, "No pude extraer datos de este archivo. Asegurate de que sea una cotizacion/lista de precios legible.")
                return

            lines = extraction["lines"]
            meta = extraction.get("metadata", {})
            print(f"[TG] Extracted {len(lines)} items from {filename}")

            # Build summary message for the agent to process
            items_text = "\n".join(
                f"- {l.get('name','?')} | {l.get('uom','pza')} | {l.get('price',0)} Bs"
                + (f" | marca: {l['brand']}" if l.get('brand') else "")
                for l in lines
            )

            supplier_hint = text.strip() if text.strip() else ""
            agent_msg = (
                f"COTIZACION RECIBIDA POR FOTO ({len(lines)} items extraidos).\n"
                f"{'Proveedor/contexto: ' + supplier_hint + chr(10) if supplier_hint else ''}"
                f"Items:\n{items_text}\n\n"
                f"Registra estos items: crea el proveedor si se menciono, busca/crea los productos "
                f"y registra los precios. Responde con un resumen de lo registrado."
            )

            # Pass extracted data as context for the agent
            response = await execute_agent_message(
                db, agent_msg, ai_config, agent_prompt,
                extracted_items=lines,
            )
            if response:
                await send_telegram(chat_id, response)
            else:
                # Fallback: just report extraction results
                summary = f"Extraidos {len(lines)} items:\n\n"
                for i, l in enumerate(lines[:15], 1):
                    summary += f"{i}. {l.get('name','?')} — {l.get('price',0)} Bs/{l.get('uom','pza')}\n"
                if len(lines) > 15:
                    summary += f"... y {len(lines)-15} mas\n"
                summary += f"\nFuente: {meta.get('ai_provider','AI')} / {meta.get('ai_model','')}"
                await send_telegram(chat_id, summary)

        except Exception as e:
            print(f"[TG] Photo processing error: {e}")
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
