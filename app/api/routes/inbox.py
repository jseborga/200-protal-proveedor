"""Inbox (Fase 2 — Hitos A/B): vista unificada de conversaciones cliente↔operador.

A: lista sesiones activas + timeline (read-only).
B: permite enviar respuestas desde la web reutilizando mirror_operator_to_client.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_staff
from app.core.database import get_db
from app.models.conversation import ConversationSession, Message
from app.models.pedido import Pedido
from app.models.user import User

router = APIRouter()


WA_WINDOW_HOURS = 24


def _wa_window_status(session: ConversationSession) -> dict:
    """Estado de la ventana de 24h de WA para el cliente."""
    if not session.last_client_msg_at:
        return {"open": False, "seconds_left": 0}
    now = datetime.now(timezone.utc)
    last = session.last_client_msg_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    delta = now - last
    remaining = WA_WINDOW_HOURS * 3600 - int(delta.total_seconds())
    return {"open": remaining > 0, "seconds_left": max(remaining, 0)}


def _session_summary(session: ConversationSession, last_msg: Message | None, pedido: Pedido | None, client_name: str | None) -> dict:
    preview = None
    if last_msg:
        body = (last_msg.body or "").strip()
        if body:
            preview = body[:140]
        elif last_msg.media_type:
            preview = f"[{last_msg.media_type}]"
    last_at = None
    if last_msg:
        last_at = last_msg.created_at
    elif session.last_client_msg_at:
        last_at = session.last_client_msg_at

    return {
        "id": session.id,
        "pedido_id": session.pedido_id,
        "pedido_ref": pedido.reference if pedido else None,
        "pedido_title": pedido.title if pedido else None,
        "state": session.state,
        "client_phone": session.client_phone,
        "client_name": client_name,
        "operator_id": session.operator_id,
        "tg_group_id": session.tg_group_id,
        "tg_topic_id": session.tg_topic_id,
        "last_msg_at": last_at.isoformat() if last_at else None,
        "last_msg_preview": preview,
        "last_msg_direction": last_msg.direction if last_msg else None,
        "last_client_msg_at": session.last_client_msg_at.isoformat() if session.last_client_msg_at else None,
        "wa_window": _wa_window_status(session),
    }


def _message_to_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "direction": m.direction,
        "channel": m.channel,
        "sender_type": m.sender_type,
        "sender_ref": m.sender_ref,
        "body": m.body,
        "media_type": m.media_type,
        "media_url": m.media_url,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


# ── GET /sessions ─────────────────────────────────────────────
@router.get("/sessions")
async def list_sessions(
    state: str | None = Query(None, description="Filtro por estado; 'open' agrupa no cerradas"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    """Lista sesiones de conversación para el inbox.

    Ordenadas por last_client_msg_at desc (NULLS LAST). Devuelve preview del
    último mensaje para que el panel izquierdo pueda renderizar sin otra query.
    """
    stmt = select(ConversationSession)
    if state == "open":
        stmt = stmt.where(ConversationSession.state != "closed")
    elif state:
        stmt = stmt.where(ConversationSession.state == state)

    # NULLS LAST: sesiones sin mensaje cliente van al final
    stmt = stmt.order_by(
        ConversationSession.last_client_msg_at.desc().nullslast(),
        ConversationSession.id.desc(),
    ).limit(limit).offset(offset)

    sessions = (await db.execute(stmt)).scalars().all()
    if not sessions:
        return {"ok": True, "data": [], "total": 0}

    # Fetch pedidos + client users in batch
    pedido_ids = {s.pedido_id for s in sessions}
    client_user_ids = {s.client_user_id for s in sessions if s.client_user_id}

    pedidos_by_id: dict[int, Pedido] = {}
    if pedido_ids:
        p_stmt = select(Pedido).where(Pedido.id.in_(pedido_ids)).options(
            selectinload(Pedido.creator)
        )
        for p in (await db.execute(p_stmt)).scalars().all():
            pedidos_by_id[p.id] = p

    users_by_id: dict[int, User] = {}
    if client_user_ids:
        u_stmt = select(User).where(User.id.in_(client_user_ids))
        for u in (await db.execute(u_stmt)).scalars().all():
            users_by_id[u.id] = u

    # Last message per session — single query
    last_msg_subq = (
        select(
            Message.session_id,
            func.max(Message.id).label("max_id"),
        )
        .where(Message.session_id.in_({s.id for s in sessions}))
        .group_by(Message.session_id)
        .subquery()
    )
    last_msgs_stmt = select(Message).join(
        last_msg_subq, Message.id == last_msg_subq.c.max_id
    )
    last_msgs_by_sid: dict[int, Message] = {}
    for m in (await db.execute(last_msgs_stmt)).scalars().all():
        last_msgs_by_sid[m.session_id] = m

    data = []
    for s in sessions:
        pedido = pedidos_by_id.get(s.pedido_id)
        # Prefer client_user name, fallback to pedido creator
        client_name = None
        if s.client_user_id and s.client_user_id in users_by_id:
            client_name = users_by_id[s.client_user_id].full_name
        elif pedido and pedido.creator:
            client_name = pedido.creator.full_name
        data.append(_session_summary(s, last_msgs_by_sid.get(s.id), pedido, client_name))

    # Total count (for UI pagination)
    count_stmt = select(func.count(ConversationSession.id))
    if state == "open":
        count_stmt = count_stmt.where(ConversationSession.state != "closed")
    elif state:
        count_stmt = count_stmt.where(ConversationSession.state == state)
    total = (await db.execute(count_stmt)).scalar() or 0

    return {"ok": True, "data": data, "total": total}


# ── GET /sessions/{id} ─────────────────────────────────────────
@router.get("/sessions/{session_id}")
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    """Detalle de una sesión: metadata + timeline de mensajes ordenado."""
    session = await db.get(ConversationSession, session_id)
    if session is None:
        raise HTTPException(404, "Sesión no encontrada")

    pedido_stmt = select(Pedido).where(Pedido.id == session.pedido_id).options(
        selectinload(Pedido.creator)
    )
    pedido = (await db.execute(pedido_stmt)).scalar_one_or_none()

    client_name = None
    if session.client_user_id:
        cu = await db.get(User, session.client_user_id)
        if cu:
            client_name = cu.full_name
    if not client_name and pedido and pedido.creator:
        client_name = pedido.creator.full_name

    msgs_stmt = select(Message).where(
        Message.session_id == session_id
    ).order_by(Message.id.asc())
    messages = (await db.execute(msgs_stmt)).scalars().all()

    summary = _session_summary(
        session,
        messages[-1] if messages else None,
        pedido,
        client_name,
    )
    summary["messages"] = [_message_to_dict(m) for m in messages]
    return {"ok": True, "data": summary}


# ── POST /sessions/{id}/send (Hito B) ──────────────────────────
class InboxSendIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


@router.post("/sessions/{session_id}/send")
async def send_from_inbox(
    session_id: int,
    payload: InboxSendIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    """Enviar un mensaje de texto al cliente desde la web.

    Respeta la ventana 24h de WA. Registra el mensaje como outbound/operator
    en el log de la sesión. Devuelve mode="whatsapp" si se entregó, o
    "window_closed"/"no_phone"/"closed" en caso contrario.
    """
    session = await db.get(ConversationSession, session_id)
    if session is None:
        raise HTTPException(404, "Sesión no encontrada")

    if session.state == "closed":
        return {"ok": False, "mode": "closed", "detail": "La sesión está cerrada"}
    if not session.client_phone:
        return {"ok": False, "mode": "no_phone", "detail": "No hay teléfono del cliente"}

    from app.services.conversation_hub import mirror_operator_to_client, is_wa_window_open

    if not is_wa_window_open(session):
        return {"ok": False, "mode": "window_closed", "detail": "Ventana WA de 24h cerrada"}

    sent = await mirror_operator_to_client(
        db, session, payload.text, operator_ref=str(user.id),
    )
    if not sent:
        await db.rollback()
        return {"ok": False, "mode": "error", "detail": "No se pudo enviar al WhatsApp del cliente"}

    # Mirror al topic de TG para que el equipo vea lo que envio desde web
    if session.tg_group_id and session.tg_topic_id:
        try:
            from app.services.messaging import send_telegram
            name = user.full_name or user.email or f"user#{user.id}"
            await send_telegram(
                session.tg_group_id,
                f"<i>💻 Web · {name}</i>\n{payload.text}",
                message_thread_id=session.tg_topic_id,
            )
        except Exception as e:
            print(f"[inbox] mirror to TG failed: {e}")

    await db.commit()
    return {"ok": True, "mode": "whatsapp"}
