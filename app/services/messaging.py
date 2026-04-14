"""Servicio de mensajeria multicanal: WhatsApp (Evolution API), Telegram, Email.

Envio de RFQs a proveedores y recepcion de respuestas.
"""

import httpx
import aiosmtplib
from email.message import EmailMessage

from app.core.config import settings


# ── WhatsApp (Evolution API) ────────────────────────────────────
async def send_whatsapp(phone: str, message: str) -> bool:
    """Send WhatsApp message via Evolution API."""
    if not settings.evolution_api_url or not settings.evolution_api_key:
        return False

    url = f"{settings.evolution_api_url}/message/sendText/{settings.evolution_instance_name}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                headers={
                    "apikey": settings.evolution_api_key,
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


async def send_whatsapp_file(phone: str, file_url: str, caption: str) -> bool:
    """Send file via WhatsApp."""
    if not settings.evolution_api_url or not settings.evolution_api_key:
        return False

    url = f"{settings.evolution_api_url}/message/sendMedia/{settings.evolution_instance_name}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                headers={
                    "apikey": settings.evolution_api_key,
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
async def send_telegram(chat_id: str, message: str) -> bool:
    """Send Telegram message."""
    if not settings.telegram_bot_token:
        return False

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            )
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


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


# ── Webhook handlers ───────────────────────────────────────────
async def handle_whatsapp_message(db, msg: dict):
    """Process incoming WhatsApp message (could be a quotation response)."""
    remote_jid = msg.get("key", {}).get("remoteJid", "")
    phone = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid
    text = msg.get("message", {}).get("conversation") or msg.get("message", {}).get("extendedTextMessage", {}).get("text", "")

    if not text:
        return

    # TODO: match phone to supplier, parse response as quotation items
    # For now, log the message
    print(f"[WA] {phone}: {text}")


async def handle_telegram_message(db, msg: dict):
    """Process incoming Telegram message."""
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = msg.get("text", "")

    if not text:
        return

    # TODO: match chat_id to supplier, parse response
    print(f"[TG] {chat_id}: {text}")
