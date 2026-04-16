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


async def send_telegram(
    chat_id: str,
    message: str,
    buttons: list[list[dict]] | None = None,
) -> bool:
    """Send Telegram message with optional inline keyboard buttons.

    buttons format: [[{"text": "Label", "callback_data": "cmd"}], ...]
    Each inner list is a row of buttons.
    """
    token = await _resolve_telegram_token()
    if not token:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}

    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
        return resp.status_code == 200
    except httpx.HTTPError:
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

            # Check AI config before extraction
            from app.services.ai_extract import extract_quotation_data, resolve_all_ai_configs
            ai_configs = await resolve_all_ai_configs()
            if not ai_configs:
                await send_telegram(
                    chat_id,
                    "No hay proveedor de IA configurado.\n"
                    "Configura Google AI Studio u otro en Admin > IA.",
                    buttons=[[{"text": "Diagnostico IA", "callback_data": "cmd_diagnostico"}]],
                )
                return

            extraction = await extract_quotation_data(content, filename, source_type)

            if not extraction or not extraction.get("lines"):
                provider = ai_configs[0].get("provider", "?")
                model = ai_configs[0].get("model", "?")
                await send_telegram(
                    chat_id,
                    f"No pude extraer datos de este archivo.\n\n"
                    f"<b>IA usada:</b> {provider} / {model}\n"
                    f"<b>Tipo:</b> {source_type} ({len(content)} bytes)\n\n"
                    f"Posibles causas:\n"
                    f"- La imagen no es legible o esta borrosa\n"
                    f"- No es una cotizacion/factura/lista de precios\n"
                    f"- Error en el proveedor de IA\n\n"
                    f"Usa /diagnostico para verificar que la IA funciona.",
                    buttons=[[{"text": "Diagnostico IA", "callback_data": "cmd_diagnostico"}]],
                )
                return

            lines = extraction["lines"]
            meta = extraction.get("metadata", {})
            extracted_supplier = extraction.get("supplier")  # {name, nit, phone, address}
            extracted_doc = extraction.get("document")  # {type, number, date}
            print(f"[TG] Extracted {len(lines)} items from {filename}"
                  + (f" | supplier: {extracted_supplier.get('name')}" if extracted_supplier else "")
                  + (f" | doc: {extracted_doc.get('type')}" if extracted_doc else ""))

            # Build supplier hint from user text + AI extraction
            user_hint = text.strip() if text.strip() else ""
            supplier_name = ""
            if extracted_supplier and extracted_supplier.get("name"):
                supplier_name = extracted_supplier["name"]
            elif user_hint:
                supplier_name = user_hint

            # Build summary for user
            doc_type = (extracted_doc or {}).get("type", media_label)
            doc_label = {"factura": "Factura", "cotizacion": "Cotizacion", "proforma": "Proforma",
                         "lista_precios": "Lista de Precios", "nota_venta": "Nota de Venta"}.get(doc_type, media_label.capitalize())
            summary = f"{doc_label}"
            if extracted_doc and extracted_doc.get("number"):
                summary += f" #{extracted_doc['number']}"
            if supplier_name:
                summary += f" — {supplier_name}"
            summary += f"\nExtraidos {len(lines)} items:\n\n"
            for i, l in enumerate(lines[:10], 1):
                qty = l.get('quantity', 1) or 1
                price_str = f"{l.get('price', 0)} Bs/{l.get('uom', 'pza')}"
                if qty != 1:
                    price_str = f"{qty} x {price_str}"
                summary += f"{i}. {l.get('name', '?')} — {price_str}"
                if l.get('brand'):
                    summary += f" ({l['brand']})"
                summary += "\n"
            if len(lines) > 10:
                summary += f"... y {len(lines)-10} mas\n"

            # ── Try Claude Code Routine first (full intelligence) ──
            from app.services.agent_executor import fire_routine
            import json as _json

            # Build rich context for the routine
            routine_data = {"items": lines}
            if extracted_supplier:
                routine_data["supplier"] = extracted_supplier
            if extracted_doc:
                routine_data["document"] = extracted_doc

            items_json = _json.dumps(routine_data, ensure_ascii=False)

            supplier_instruction = ""
            if supplier_name:
                supplier_instruction = (
                    f"Proveedor detectado: '{supplier_name}'"
                    + (f" (NIT: {extracted_supplier['nit']})" if extracted_supplier and extracted_supplier.get('nit') else "")
                    + ". Busca con list_suppliers si ya existe. "
                    "Si no existe, crealo con create_supplier.\n"
                )
            else:
                supplier_instruction = "No se detecto proveedor. Si los items sugieren uno, crealo. Sino, registra precios sin proveedor.\n"

            routine_task = (
                f"PROCESAR {'FACTURA' if doc_type == 'factura' else 'COTIZACION'} recibida por Telegram.\n\n"
                f"{supplier_instruction}"
                f"Se extrajeron {len(lines)} items de una {doc_label.lower()}.\n\n"
                f"DATOS EXTRAIDOS (JSON):\n{items_json}\n\n"
                f"INSTRUCCIONES:\n"
                f"1. {supplier_instruction}"
                f"2. Para cada item, busca con list_products si el producto ya existe en el catalogo. "
                f"Considera variaciones de nombre (ej: 'Cemento IP-30' vs 'CEMENTO PORTLAND IP-30').\n"
                f"3. Clasifica cada item en la categoria correcta: "
                f"ferreteria, agregados, acero, electrico, sanitario, madera, cemento, pintura, ceramica, herramientas, techos, plomeria, vidrios, prefabricados.\n"
                f"4. Los productos que NO existan, crealos con create_products_bulk (nombre limpio, unidad correcta, categoria, precio como ref_price).\n"
                f"5. Registra TODOS los precios con create_price_history_bulk "
                f"(source: 'telegram', observed_date: hoy, supplier_name: '{supplier_name}' si se conoce).\n"
                f"6. Al final, reporta un resumen: cuantos productos nuevos, existentes, precios registrados.\n"
            )

            routine_result = await fire_routine(db, routine_task)

            if routine_result.get("estado") == "iniciada":
                session_url = routine_result.get("url", "")
                summary += (
                    f"\nDelegado a Claude Code para procesar inteligentemente.\n"
                    f"(verificar proveedores, clasificar, registrar precios)\n"
                )
                if session_url:
                    summary += f"\nSesion: {session_url}"
                await send_telegram(chat_id, summary)
            else:
                # Routine not configured or failed — fallback to simple agent
                routine_error = routine_result.get("error", "")
                print(f"[TG] Routine unavailable ({routine_error}), falling back to agent")

                items_text = "\n".join(
                    f"- {l.get('name','?')} | {l.get('uom','pza')} | {l.get('price',0)} Bs"
                    + (f" | marca: {l['brand']}" if l.get('brand') else "")
                    for l in lines
                )
                agent_msg = (
                    f"{doc_label.upper()} RECIBIDA ({len(lines)} items extraidos).\n"
                    f"{'Proveedor: ' + supplier_name + chr(10) if supplier_name else ''}"
                    f"Items:\n{items_text}\n\n"
                    f"Registra estos items usando registrar_cotizacion: busca/crea el proveedor, "
                    f"busca/crea los productos y registra los precios."
                )

                response = await execute_agent_message(
                    db, agent_msg, ai_config, agent_prompt,
                    extracted_items=lines,
                )
                if response:
                    await send_telegram(chat_id, response)
                else:
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
    """Process a completed batch: download, extract, merge, delegate."""
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
        + "..."
    )

    # ── Download and extract from each media file ───────────────
    from app.services.ai_extract import extract_quotation_data

    all_lines = []
    all_suppliers = []
    all_docs = []
    extraction_errors = []

    for idx, item in enumerate(media_items, 1):
        file_id = item["file_id"]
        filename = item.get("filename", "archivo")
        mime = item.get("mime_type", item.get("mime", ""))

        # Determine source_type
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

        # Download
        dl = await _download_telegram_file(file_id)
        if not dl:
            extraction_errors.append(f"No pude descargar {filename}")
            continue
        content, file_path = dl
        print(f"[TG-Batch] Downloaded #{idx}: {len(content)} bytes ({file_path})")

        # Extract
        try:
            extraction = await extract_quotation_data(content, filename, source_type)
        except Exception as e:
            print(f"[TG-Batch] Extraction error for #{idx}: {e}")
            extraction_errors.append(f"Error extrayendo {filename}: {str(e)[:80]}")
            continue

        if not extraction or not extraction.get("lines"):
            extraction_errors.append(f"Sin datos en {filename}")
            continue

        lines = extraction["lines"]
        supplier = extraction.get("supplier")
        doc_info = extraction.get("document")

        # Tag each line with its source file
        for line in lines:
            line["_source_file"] = filename
            line["_source_idx"] = idx

        all_lines.extend(lines)
        if supplier and supplier.get("name"):
            all_suppliers.append(supplier)
        if doc_info:
            all_docs.append(doc_info)

        print(f"[TG-Batch] #{idx}: {len(lines)} items"
              + (f" | supplier: {supplier.get('name')}" if supplier else "")
              + (f" | doc: {doc_info.get('type')}" if doc_info else ""))

    # ── Build user summary ──────────────────────────────────────
    if not all_lines:
        error_detail = "\n".join(f"- {e}" for e in extraction_errors) if extraction_errors else "Sin detalles"
        await send_telegram(
            chat_id,
            f"No se pudieron extraer datos del lote.\n\n{error_detail}"
        )
        return

    # Deduplicate suppliers by name
    unique_suppliers = {}
    for s in all_suppliers:
        name = s.get("name", "").strip().lower()
        if name and name not in unique_suppliers:
            unique_suppliers[name] = s
    supplier_list = list(unique_suppliers.values())

    # Primary supplier (most mentioned or from description)
    primary_supplier_name = ""
    if supplier_list:
        primary_supplier_name = supplier_list[0].get("name", "")
    elif desc:
        primary_supplier_name = desc

    summary = "<b>Lote procesado</b>\n"
    if desc:
        summary += f"Descripcion: {desc}\n"
    summary += f"Archivos: {len(media_items)} | Items extraidos: {len(all_lines)}\n"
    if supplier_list:
        names = ", ".join(s.get("name", "?") for s in supplier_list)
        summary += f"Proveedores detectados: {names}\n"
    if all_docs:
        doc_labels = []
        for d in all_docs:
            label = {"factura": "Factura", "cotizacion": "Cotizacion", "proforma": "Proforma",
                     "lista_precios": "Lista", "nota_venta": "Nota"}.get(d.get("type", ""), "Doc")
            if d.get("number"):
                label += f" #{d['number']}"
            doc_labels.append(label)
        summary += f"Documentos: {', '.join(doc_labels)}\n"
    if text_notes:
        summary += f"Notas del usuario: {len(text_notes)}\n"
    if extraction_errors:
        summary += f"Errores: {len(extraction_errors)}\n"

    summary += f"\nItems (primeros 15):\n"
    for i, l in enumerate(all_lines[:15], 1):
        qty = l.get('quantity', 1) or 1
        price_str = f"{l.get('price', 0)} Bs/{l.get('uom', 'pza')}"
        if qty != 1:
            price_str = f"{qty} x {price_str}"
        summary += f"{i}. {l.get('name', '?')} — {price_str}\n"
    if len(all_lines) > 15:
        summary += f"... y {len(all_lines) - 15} mas\n"

    # ── Delegate to Routine or Agent ────────────────────────────
    import json as _json
    from app.services.agent_executor import fire_routine

    # Build rich data payload
    routine_data = {"items": all_lines}
    if supplier_list:
        routine_data["suppliers"] = supplier_list
    if all_docs:
        routine_data["documents"] = all_docs
    if text_notes:
        routine_data["user_notes"] = text_notes

    items_json = _json.dumps(routine_data, ensure_ascii=False)

    # Build supplier instructions
    if supplier_list:
        supplier_parts = []
        for s in supplier_list:
            part = f"'{s.get('name', '?')}'"
            if s.get("nit"):
                part += f" (NIT: {s['nit']})"
            if s.get("phone"):
                part += f" (Tel: {s['phone']})"
            supplier_parts.append(part)
        supplier_instruction = (
            f"Proveedores detectados: {', '.join(supplier_parts)}. "
            "Para cada proveedor, busca con list_suppliers si ya existe. "
            "Si no existe, crealo con create_supplier.\n"
        )
    elif primary_supplier_name:
        supplier_instruction = (
            f"Posible proveedor (de la descripcion del lote): '{primary_supplier_name}'. "
            "Busca con list_suppliers si ya existe. Si no existe, crealo.\n"
        )
    else:
        supplier_instruction = (
            "No se detecto proveedor. Si los items o notas sugieren uno, crealo. "
            "Sino, registra precios sin proveedor.\n"
        )

    notes_text = ""
    if text_notes:
        notes_text = f"\nNOTAS DEL USUARIO:\n" + "\n".join(f"- {n}" for n in text_notes) + "\n"

    doc_type_label = "DOCUMENTOS" if len(media_items) > 1 else "DOCUMENTO"
    routine_task = (
        f"PROCESAR LOTE de {len(media_items)} {doc_type_label} recibidos por Telegram.\n"
        + (f"Descripcion del lote: {desc}\n" if desc else "")
        + f"\n{supplier_instruction}"
        + f"Se extrajeron {len(all_lines)} items en total de {len(media_items)} archivos.\n"
        + notes_text
        + f"\nDATOS EXTRAIDOS (JSON):\n{items_json}\n\n"
        f"INSTRUCCIONES:\n"
        f"1. {supplier_instruction}"
        f"2. Para cada item, busca con list_products si el producto ya existe en el catalogo. "
        f"Considera variaciones de nombre (ej: 'Cemento IP-30' vs 'CEMENTO PORTLAND IP-30').\n"
        f"3. Clasifica cada item en la categoria correcta: "
        f"ferreteria, agregados, acero, electrico, sanitario, madera, cemento, pintura, ceramica, herramientas, techos, plomeria, vidrios, prefabricados.\n"
        f"4. Los productos que NO existan, crealos con create_products_bulk (nombre limpio, unidad correcta, categoria, precio como ref_price).\n"
        f"5. Registra TODOS los precios con create_price_history_bulk "
        f"(source: 'telegram_batch', observed_date: hoy"
        + (f", supplier_name del proveedor correspondiente" if supplier_list else "")
        + f").\n"
        f"6. Al final, reporta un resumen: cuantos productos nuevos, existentes, precios registrados, por proveedor si hay varios.\n"
    )

    routine_result = await fire_routine(db, routine_task)

    if routine_result.get("estado") == "iniciada":
        session_url = routine_result.get("url", "")
        summary += (
            "\nDelegado a Claude Code para procesar inteligentemente.\n"
            "(verificar proveedores, clasificar, registrar precios)\n"
        )
        if session_url:
            summary += f"\nSesion: {session_url}"
        await send_telegram(chat_id, summary)
    else:
        # Fallback to simple agent
        routine_error = routine_result.get("error", "")
        print(f"[TG-Batch] Routine unavailable ({routine_error}), falling back to agent")

        try:
            from app.services.agent_executor import execute_agent_message, resolve_agent_config
            result = await resolve_agent_config(db, "communicator")
            if result and result[0]:
                ai_config, agent_prompt = result

                items_text = "\n".join(
                    f"- {l.get('name','?')} | {l.get('uom','pza')} | {l.get('price',0)} Bs"
                    + (f" | marca: {l['brand']}" if l.get('brand') else "")
                    for l in all_lines
                )
                agent_msg = (
                    f"LOTE DE {len(media_items)} DOCUMENTOS ({len(all_lines)} items extraidos).\n"
                    + (f"Descripcion: {desc}\n" if desc else "")
                    + (f"Proveedor principal: {primary_supplier_name}\n" if primary_supplier_name else "")
                    + (f"Notas: {'; '.join(text_notes)}\n" if text_notes else "")
                    + f"Items:\n{items_text}\n\n"
                    f"Registra estos items usando registrar_cotizacion: busca/crea los proveedores, "
                    f"busca/crea los productos y registra los precios."
                )

                response = await execute_agent_message(
                    db, agent_msg, ai_config, agent_prompt,
                    extracted_items=all_lines,
                )
                if response:
                    await send_telegram(chat_id, response)
                    return
        except Exception as e:
            print(f"[TG-Batch] Agent fallback error: {e}")

        # Last resort: just send the summary
        await send_telegram(chat_id, summary)


# ── Callback handler (inline button clicks) ──────────────────

async def handle_telegram_callback(db, callback: dict):
    """Handle inline keyboard button presses."""
    callback_id = callback.get("id", "")
    chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
    data = callback.get("data", "")
    username = callback.get("from", {}).get("username", "")

    print(f"[TG-CB] {chat_id} (@{username}): {data}")

    # Always acknowledge the callback to dismiss the loading spinner
    await _answer_callback(callback_id)

    if not chat_id:
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
