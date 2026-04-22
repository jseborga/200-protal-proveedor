"""Conversation Hub — orquesta conversaciones cliente↔operador sobre un Pedido.

Arquitectura:
- Cliente habla por WhatsApp con el bot (iniciado vía wa.me link).
- Bot/sistema espeja cada mensaje al grupo de Telegram de operadores dentro
  de un *topic* (foro) dedicado al pedido.
- El operador responde en el topic; el hub reenvía al WA del cliente.
- Bot responde automáticamente con plantillas mientras el operador cotiza.

Estados de ConversationSession:
- waiting_first_contact: pedido creado, esperando 1er mensaje del cliente
- active: cliente inició WA, ventana 24h abierta, sin operador aún
- operator_engaged: operador tomó y está respondiendo — bot silencioso
- quote_sent: cotización entregada al cliente
- closed: flujo terminado (manual o por timeout)
"""

from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import ConversationSession, Message
from app.models.pedido import Pedido
from app.models.user import User
from app.services.messaging import (
    _resolve_hub_group_id,
    create_telegram_topic,
    close_telegram_topic,
    send_email,
    send_telegram,
    send_whatsapp,
)


async def _resolve_bot_wa_number() -> str | None:
    """Resuelve el número WA público del bot desde system_setting.integrations."""
    try:
        from app.core.database import async_session
        from app.models.system_setting import SystemSetting
        async with async_session() as db:
            setting = await db.get(SystemSetting, "integrations")
            cfg = setting.value if setting and setting.value else {}
        num = cfg.get("conversation_hub_bot_wa_number")
        if num:
            return str(num).replace(" ", "").replace("-", "").replace("+", "")
    except Exception:
        pass
    return None


async def build_wa_confirmation_url(pedido: Pedido, user: User | None = None) -> str | None:
    """Generar wa.me URL prellenada para que el cliente inicie la conversación.

    Devuelve None si el número del bot no está configurado — el frontend
    debe caer a una vista sin botón WA.
    """
    number = await _resolve_bot_wa_number()
    if not number:
        return None
    name = user.full_name if user and user.full_name else "cliente"
    text = f"Hola, soy {name}. Confirmo mi pedido {pedido.reference}."
    return f"https://wa.me/{number}?text={quote(text)}"


WA_WINDOW_HOURS = 24

_AUTOREPLY_TEMPLATES_WAITING = [
    "Gracias por escribir. Estamos procesando tu solicitud <b>{ref}</b>, te respondemos apenas tengamos la cotización.",
    "Recibimos tu mensaje. Tu pedido <b>{ref}</b> ya está en manos de nuestro equipo, en breve te llegan los precios.",
    "Seguimos trabajando en tu pedido <b>{ref}</b>. Gracias por la paciencia — te avisamos apenas esté listo.",
    "Tu pedido <b>{ref}</b> está siendo cotizado. Te contactamos en cuanto tengamos las respuestas de los proveedores.",
]

# Keywords que sugieren que el cliente necesita atención humana específica.
# No es matching sofisticado, solo triggers comunes en español boliviano.
_ATTENTION_KEYWORDS = (
    "urgente", "urgen", "rapido", "rápido", "ya mismo", "ahora",
    "cuanto", "cuánto", "precio", "costo", "cuesta",
    "plazo", "cuando", "cuándo", "tiempo",
    "disponib", "stock", "tienen", "hay ",
    "problema", "error", "mal ", "queja", "reclamo",
    "factura", "nit ", "nit:",
)


# ── Helpers ────────────────────────────────────────────────────

def _normalize_phone(phone: str | None) -> str | None:
    """Normalize WA phone to digits-only with country code."""
    if not phone:
        return None
    p = phone.strip().replace(" ", "").replace("-", "").replace("+", "")
    if "@" in p:
        p = p.split("@")[0]
    if not p.startswith("591") and len(p) == 8:
        p = "591" + p
    return p or None


def is_wa_window_open(session: ConversationSession) -> bool:
    """True si la ventana de 24h de WhatsApp sigue abierta."""
    if session.last_client_msg_at is None:
        return False
    last = session.last_client_msg_at if session.last_client_msg_at.tzinfo else session.last_client_msg_at.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - last
    return delta < timedelta(hours=WA_WINDOW_HOURS)


# ── Session management ─────────────────────────────────────────

async def open_session(
    db: AsyncSession,
    pedido: Pedido,
    client_phone: str | None = None,
) -> ConversationSession | None:
    """Abrir una nueva ConversationSession para un Pedido recién creado.

    Crea el topic en el grupo TG de operadores y postea el resumen inicial
    con botón inline "Tomar". Devuelve la session (o None si no hay grupo
    configurado, en cuyo caso el flujo TG simplemente no opera pero el
    pedido vive igual en el portal).
    """
    group_id = await _resolve_hub_group_id()
    tg_topic_id: int | None = None

    if group_id:
        topic_name = f"{pedido.reference} — {pedido.title[:80]}"
        tg_topic_id = await create_telegram_topic(group_id, topic_name)

    session = ConversationSession(
        pedido_id=pedido.id,
        client_user_id=pedido.created_by,
        client_phone=_normalize_phone(client_phone or pedido.client_whatsapp),
        tg_group_id=group_id,
        tg_topic_id=tg_topic_id,
        state="waiting_first_contact",
    )
    db.add(session)
    await db.flush()

    # Persist topic_id on Pedido for quick lookup
    if tg_topic_id is not None:
        pedido.tg_topic_id = tg_topic_id

    # Post the pedido summary into the topic with a Take button
    if group_id and tg_topic_id is not None:
        summary = _build_pedido_summary(pedido)
        await send_telegram(
            group_id,
            summary,
            buttons=[[
                {"text": "Tomar este pedido", "callback_data": f"cb_claim_pedido_{pedido.id}"},
            ]],
            message_thread_id=tg_topic_id,
        )

    return session


def _build_pedido_summary(pedido: Pedido) -> str:
    """Build the initial topic message with items listed."""
    lines = [f"<b>Pedido {pedido.reference}</b>", f"<b>Título:</b> {pedido.title}"]
    if pedido.description:
        desc = pedido.description[:300]
        lines.append(f"<b>Descripción:</b> {desc}")
    if pedido.region:
        lines.append(f"<b>Región:</b> {pedido.region}")
    if pedido.deadline:
        lines.append(f"<b>Fecha límite:</b> {pedido.deadline.strftime('%d/%m/%Y')}")
    if pedido.client_whatsapp:
        lines.append(f"<b>Cliente WA:</b> {pedido.client_whatsapp}")

    items = list(pedido.items) if pedido.items else []
    if items:
        lines.append(f"\n<b>Items ({len(items)}):</b>")
        for it in items[:20]:
            price = f" (ref: {it.ref_price} {pedido.currency})" if it.ref_price else ""
            lines.append(f"• {it.name} — {it.quantity} {it.uom or 'und'}{price}")
        if len(items) > 20:
            lines.append(f"… y {len(items) - 20} items más")

    lines.append("\nUsá el botón para tomar este pedido.")
    return "\n".join(lines)


async def find_active_session_for_client(
    db: AsyncSession,
    client_phone: str,
) -> ConversationSession | None:
    """Buscar la sesión activa más reciente para un número WA entrante."""
    norm = _normalize_phone(client_phone)
    if not norm:
        return None
    stmt = (
        select(ConversationSession)
        .where(
            ConversationSession.client_phone == norm,
            ConversationSession.state.in_([
                "waiting_first_contact", "active", "operator_engaged", "quote_sent",
            ]),
        )
        .order_by(ConversationSession.id.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def find_session_by_topic(
    db: AsyncSession,
    group_id: str,
    topic_id: int,
) -> ConversationSession | None:
    """Buscar sesión por topic_id (para mensajes entrantes del operador)."""
    stmt = select(ConversationSession).where(
        ConversationSession.tg_group_id == str(group_id),
        ConversationSession.tg_topic_id == topic_id,
    ).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ── Message logging ────────────────────────────────────────────

async def record_message(
    db: AsyncSession,
    session: ConversationSession,
    *,
    direction: str,
    channel: str,
    sender_type: str,
    sender_ref: str | None = None,
    body: str | None = None,
    media_url: str | None = None,
    media_type: str | None = None,
    ext_message_id: str | None = None,
) -> Message:
    """Persist a message in the session log and update timestamps."""
    msg = Message(
        session_id=session.id,
        direction=direction,
        channel=channel,
        sender_type=sender_type,
        sender_ref=sender_ref,
        body=body,
        media_url=media_url,
        media_type=media_type,
        ext_message_id=ext_message_id,
    )
    db.add(msg)

    now = datetime.now(timezone.utc)
    if direction == "inbound" and sender_type == "client":
        session.last_client_msg_at = now
    elif direction == "outbound" and sender_type == "operator":
        session.last_operator_msg_at = now

    await db.flush()
    return msg


# ── Bridging ───────────────────────────────────────────────────

async def mirror_client_to_topic(
    db: AsyncSession,
    session: ConversationSession,
    text: str | None,
    sender_ref: str | None = None,
    media_note: str | None = None,
    media_bytes: bytes | None = None,
    media_mime: str | None = None,
    media_filename: str | None = None,
) -> None:
    """Forward a client WA message into the TG operator topic.

    Si hay media_bytes, sube el archivo al topic (foto/documento/audio) con
    la caption apropiada. Si solo hay media_note (fallback), envia texto.
    """
    if not session.tg_group_id or not session.tg_topic_id:
        return

    prefix = f"<i>📱 Cliente</i>"

    if media_bytes:
        from app.services.messaging import send_telegram_media_bytes_to_topic
        mime = (media_mime or "").lower()
        if mime.startswith("image/") and not mime.endswith("webp"):
            kind = "photo"
        elif mime.startswith("audio/"):
            kind = "audio"
        elif mime.startswith("video/"):
            kind = "video"
        else:
            kind = "document"
        caption_parts = [prefix]
        if media_note:
            caption_parts.append(f"<i>[{media_note}]</i>")
        if text:
            caption_parts.append(text)
        caption = "\n".join(caption_parts)
        ok = await send_telegram_media_bytes_to_topic(
            session.tg_group_id,
            session.tg_topic_id,
            media_bytes,
            media_filename or "archivo",
            media_mime or "application/octet-stream",
            caption,
            kind=kind,
        )
        if ok:
            return
        # Fallback to text note if upload failed
        body = f"{prefix} <i>[{media_note or 'archivo'}]</i> (no se pudo subir)\n{text or ''}".strip()
        await send_telegram(session.tg_group_id, body, message_thread_id=session.tg_topic_id)
        return

    if media_note:
        body = f"{prefix} <i>[{media_note}]</i>\n{text or ''}".strip()
    else:
        body = f"{prefix}\n{text or ''}"

    await send_telegram(
        session.tg_group_id,
        body,
        message_thread_id=session.tg_topic_id,
    )


async def mirror_operator_to_client(
    db: AsyncSession,
    session: ConversationSession,
    text: str,
    operator_ref: str | None = None,
) -> bool:
    """Send operator's TG reply to the client's WA.

    Respeta ventana 24h: si está cerrada, no envía y devuelve False (el
    caller decide fallback — email/portal). Si está abierta, envía y
    registra el mensaje.
    """
    if not session.client_phone:
        return False
    if not is_wa_window_open(session):
        return False

    ok = await send_whatsapp(session.client_phone, text)
    if ok:
        await record_message(
            db, session,
            direction="outbound", channel="whatsapp",
            sender_type="operator", sender_ref=operator_ref, body=text,
        )
        if session.state != "operator_engaged":
            session.state = "operator_engaged"
        await db.flush()
    return ok


# ── Bot auto-reply ─────────────────────────────────────────────

def _needs_attention(text: str) -> bool:
    """Heuristica simple: ¿el cliente está pidiendo algo específico?"""
    lower = (text or "").lower()
    return any(kw in lower for kw in _ATTENTION_KEYWORDS)


async def bot_autoreply(
    db: AsyncSession,
    session: ConversationSession,
    incoming_text: str,
) -> str | None:
    """Decide qué responder automáticamente al cliente (o None si silencio).

    Reglas:
    - Si state == operator_engaged → None (bot silencioso, humano maneja).
    - Si state == quote_sent → responder cortésmente y pingear operadores.
    - Si state == waiting_first_contact o active → rotar plantillas.

    Además, si el mensaje contiene palabras que sugieren pregunta específica
    (precio, plazo, stock, urgente...) se pingea al topic con @aqui para que
    un operador preste atención en tiempo real.
    """
    if session.state == "operator_engaged":
        return None

    pedido = await db.get(Pedido, session.pedido_id)
    ref = pedido.reference if pedido else "tu solicitud"

    # Cuenta de inbound para rotar plantilla
    count_stmt = select(Message).where(
        Message.session_id == session.id,
        Message.direction == "inbound",
        Message.sender_type == "client",
    )
    inbound_count = len((await db.execute(count_stmt)).scalars().all())

    # Ping operators when the client asks something specific
    if _needs_attention(incoming_text):
        await _ping_operators(
            session,
            f"Cliente pregunta algo específico: <i>{incoming_text[:200]}</i>",
        )

    if session.state == "quote_sent":
        # Cliente sigue escribiendo después de cotización entregada
        await _ping_operators(session, f"Cliente insiste tras cotización enviada: {incoming_text[:120]}")
        return (
            f"Ya te enviamos la cotización de <b>{ref}</b>. "
            "Si tienes alguna duda específica, un agente te contactará en breve."
        )

    template = _AUTOREPLY_TEMPLATES_WAITING[inbound_count % len(_AUTOREPLY_TEMPLATES_WAITING)]
    return template.format(ref=ref)


async def _ping_operators(session: ConversationSession, text: str) -> None:
    """Pingear al topic para que un operador tome atención."""
    if not session.tg_group_id or not session.tg_topic_id:
        return
    await send_telegram(
        session.tg_group_id,
        f"⚠️ <b>Atención</b>: {text}",
        message_thread_id=session.tg_topic_id,
    )


# ── Claim (atomic lock) ────────────────────────────────────────

async def claim_pedido(
    db: AsyncSession,
    pedido_id: int,
    tg_user_id: str,
) -> User | None:
    """Lockear el pedido al usuario cuyo telegram_user_id matchea.

    Returns the User who claimed on success, or None if:
    - no registered user with that tg_user_id (no autorizado)
    - pedido ya fue tomado por otro (lost the race)
    """
    norm_tg = str(tg_user_id).strip()
    user_stmt = select(User).where(User.telegram_user_id == norm_tg).limit(1)
    user = (await db.execute(user_stmt)).scalar_one_or_none()
    if user is None:
        return None

    now = datetime.now(timezone.utc)
    claim_stmt = (
        update(Pedido)
        .where(Pedido.id == pedido_id, Pedido.assigned_to.is_(None))
        .values(assigned_to=user.id, claimed_at=now)
        .returning(Pedido.id)
    )
    claimed = (await db.execute(claim_stmt)).scalar_one_or_none()
    if claimed is None:
        return None

    # Update associated ConversationSession
    sess_stmt = (
        update(ConversationSession)
        .where(
            ConversationSession.pedido_id == pedido_id,
            ConversationSession.operator_id.is_(None),
        )
        .values(operator_id=user.id)
    )
    await db.execute(sess_stmt)
    await db.flush()
    return user


# ── Quote delivery ─────────────────────────────────────────────

QUOTE_INLINE_MAX_ITEMS = 8
QUOTE_INLINE_MAX_CHARS = 600


def _fmt_money(amount: float, currency: str) -> str:
    """Formato simple de monto: 'Bs 1,234.56'."""
    try:
        return f"{currency} {amount:,.2f}"
    except Exception:
        return f"{currency} {amount}"


def _pick_price(item) -> "PedidoPrecio | None":
    """Elegir el precio a entregar: seleccionado > menor > None."""
    precios = list(item.precios) if item.precios else []
    if not precios:
        return None
    for p in precios:
        if getattr(p, "is_selected", False):
            return p
    return min(precios, key=lambda p: p.unit_price)


def _build_quote_summary(pedido: Pedido) -> tuple[str, bool]:
    """Construir el texto de la cotización para el cliente.

    Devuelve (body, is_full). Si is_full=False, el caller debería agregar
    un link al detalle web porque se truncó la lista.
    """
    from app.core.config import settings

    lines: list[str] = []
    lines.append(f"📦 <b>Cotización {pedido.reference}</b>")
    lines.append(pedido.title)
    lines.append("")

    items = list(pedido.items) if pedido.items else []
    total = 0.0
    detail_lines: list[str] = []
    pending: list[str] = []

    for idx, it in enumerate(items, start=1):
        price = _pick_price(it)
        if price is None:
            pending.append(f"{idx}. {it.name}")
            continue
        subtotal = (it.quantity or 0) * price.unit_price
        total += subtotal
        unit = it.uom or "und"
        detail_lines.append(
            f"{idx}. {it.name} — {it.quantity} {unit} × "
            f"{_fmt_money(price.unit_price, price.currency)} = "
            f"{_fmt_money(subtotal, pedido.currency)}"
        )

    lines.extend(detail_lines)
    if pending:
        lines.append("")
        lines.append("<i>Pendientes de cotizar:</i>")
        lines.extend(f"• {p}" for p in pending)

    if detail_lines:
        lines.append("")
        lines.append(f"<b>Total: {_fmt_money(total, pedido.currency)}</b>")

    if pedido.deadline:
        lines.append(f"Válido hasta: {pedido.deadline.strftime('%d/%m/%Y')}")

    detail_url = f"{settings.app_url.rstrip('/')}/pedidos/{pedido.id}"

    body = "\n".join(lines)
    is_full = len(items) <= QUOTE_INLINE_MAX_ITEMS and len(body) <= QUOTE_INLINE_MAX_CHARS
    if not is_full:
        # Modo resumen: solo cabecera + total + link
        short_lines = [
            f"📦 <b>Cotización {pedido.reference}</b>",
            pedido.title,
        ]
        if detail_lines:
            short_lines.append(f"<b>Total: {_fmt_money(total, pedido.currency)}</b>")
        short_lines.append(f"Detalle completo: {detail_url}")
        body = "\n".join(short_lines)
    else:
        body = f"{body}\nDetalle: {detail_url}"

    return body, is_full


def _quote_body_to_html(body: str) -> str:
    """Convertir el texto de la cotización (con tags <b>) a HTML simple para email."""
    import html as _html
    # Proteger tags que ya soportamos: <b>...</b> y <i>...</i>
    placeholders = {
        "<b>": "\x00OB\x00", "</b>": "\x00CB\x00",
        "<i>": "\x00OI\x00", "</i>": "\x00CI\x00",
    }
    out = body
    for k, v in placeholders.items():
        out = out.replace(k, v)
    out = _html.escape(out)
    for k, v in placeholders.items():
        out = out.replace(v, k.replace("<b>", "<strong>").replace("</b>", "</strong>").replace("<i>", "<em>").replace("</i>", "</em>"))
    out = out.replace("\n", "<br>\n")
    return f"<div style=\"font-family:Arial,sans-serif;font-size:14px;line-height:1.5\">{out}</div>"


async def _try_email_fallback(pedido: Pedido, body: str) -> bool:
    """Intentar enviar la cotización por email al creador del pedido."""
    creator = getattr(pedido, "creator", None)
    to_addr = getattr(creator, "email", None) if creator else None
    if not to_addr:
        return False
    subject = f"Cotización {pedido.reference} — {pedido.title}"[:160]
    html = _quote_body_to_html(body)
    return await send_email(to_addr, subject, html)


async def deliver_quote_to_client(
    db: AsyncSession,
    pedido: Pedido,
    operator: User | None = None,
) -> dict:
    """Enviar la cotización final al cliente por WA con fallback a email.

    Devuelve dict con:
      - ok: bool
      - mode: "whatsapp" | "email" | "window_closed" | "no_session" | "no_phone"
      - url: detail URL del pedido
      - body: texto enviado

    Si la ventana 24h está cerrada o no hay sesión WA, intenta email al
    creador del pedido antes de devolver failure mode.
    """
    from app.core.config import settings

    sess_stmt = select(ConversationSession).where(
        ConversationSession.pedido_id == pedido.id,
    ).order_by(ConversationSession.id.desc()).limit(1)
    session = (await db.execute(sess_stmt)).scalar_one_or_none()

    body, _is_full = _build_quote_summary(pedido)
    detail_url = f"{settings.app_url.rstrip('/')}/pedidos/{pedido.id}"

    async def _email_fallback_result(mode_if_fail: str) -> dict:
        if await _try_email_fallback(pedido, body):
            # Log outbound via email if we have a session
            if session is not None:
                await record_message(
                    db, session,
                    direction="outbound", channel="email",
                    sender_type="operator" if operator else "system",
                    sender_ref=str(operator.id) if operator else None,
                    body=body,
                )
                session.state = "quote_sent"
                await db.flush()
                if session.tg_group_id and session.tg_topic_id:
                    await send_telegram(
                        session.tg_group_id,
                        f"✉️ <b>Cotización enviada por email</b> (WA no disponible)\n\n{body}",
                        message_thread_id=session.tg_topic_id,
                    )
            return {"ok": True, "mode": "email", "url": detail_url, "body": body}
        return {"ok": False, "mode": mode_if_fail, "url": detail_url, "body": body}

    if session is None:
        return await _email_fallback_result("no_session")
    if not session.client_phone:
        return await _email_fallback_result("no_phone")
    if not is_wa_window_open(session):
        # Ventana 24h cerrada — probar email antes de avisar a operadores
        result = await _email_fallback_result("window_closed")
        if not result["ok"]:
            await _ping_operators(
                session,
                "Cotización lista pero ventana 24h cerrada y sin email del cliente. "
                f"Contactar por otro canal. {detail_url}",
            )
        return result

    ok = await send_whatsapp(session.client_phone, body)
    if not ok:
        return await _email_fallback_result("whatsapp")

    await record_message(
        db, session,
        direction="outbound", channel="whatsapp",
        sender_type="operator" if operator else "system",
        sender_ref=str(operator.id) if operator else None,
        body=body,
    )
    session.state = "quote_sent"
    await db.flush()

    # Mirror al topic para que el equipo vea lo que se envió
    if session.tg_group_id and session.tg_topic_id:
        await send_telegram(
            session.tg_group_id,
            f"✅ <b>Cotización enviada al cliente</b>\n\n{body}",
            message_thread_id=session.tg_topic_id,
        )

    return {"ok": True, "mode": "whatsapp", "url": detail_url, "body": body}


# ── Close ──────────────────────────────────────────────────────

async def close_session(db: AsyncSession, session: ConversationSession) -> None:
    """Cerrar la sesión y el topic de TG (readonly)."""
    session.state = "closed"
    await db.flush()
    if session.tg_group_id and session.tg_topic_id:
        await close_telegram_topic(session.tg_group_id, session.tg_topic_id)


async def close_session_for_pedido(db: AsyncSession, pedido_id: int) -> bool:
    """Buscar y cerrar la sesión asociada a un pedido (si existe)."""
    stmt = select(ConversationSession).where(
        ConversationSession.pedido_id == pedido_id,
    ).order_by(ConversationSession.id.desc()).limit(1)
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session is None or session.state == "closed":
        return False
    await close_session(db, session)
    return True
