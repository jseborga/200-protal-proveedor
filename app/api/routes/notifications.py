"""Endpoints de notificaciones in-app."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.notification import Notification
from app.models.user import User

router = APIRouter()


def _notif_to_dict(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "is_read": n.is_read,
        "data": n.data,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@router.get("")
async def list_notifications(
    skip: int = 0,
    limit: int = 20,
    unread_only: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Listar mis notificaciones (mas recientes primero)."""
    q = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        q = q.where(Notification.is_read == False)  # noqa: E712
    q = q.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    notifs = result.scalars().all()
    return {"ok": True, "data": [_notif_to_dict(n) for n in notifs]}


@router.get("/unread-count")
async def unread_count(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Conteo de notificaciones no leidas."""
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            Notification.is_read == False,  # noqa: E712
        )
    )
    count = result.scalar() or 0
    return {"ok": True, "count": count}


@router.put("/{notif_id}/read")
async def mark_read(
    notif_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Marcar una notificacion como leida."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notif_id,
            Notification.user_id == user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Notificacion no encontrada")
    notif.is_read = True
    await db.commit()
    return {"ok": True}


@router.post("/mark-all-read")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Marcar todas las notificaciones como leidas."""
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read == False)  # noqa: E712
        .values(is_read=True)
    )
    await db.commit()
    return {"ok": True}
