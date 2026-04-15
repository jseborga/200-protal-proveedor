"""Endpoints para suscripciones."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.plans import PLANS
from app.core.security import get_current_user
from app.models.company import Subscription
from app.models.user import User

router = APIRouter()


# ── Planes disponibles ────────────────────────────────────────
@router.get("/plans")
async def list_plans():
    """Planes disponibles (datos estaticos, no requiere auth)."""
    data = []
    for key, info in PLANS.items():
        data.append({
            "key": key,
            "label": info["label"],
            "max_users": info["max_users"],
            "max_pedidos_month": info["max_pedidos_month"],
            "price_bob": info["price_bob"],
            "features": info["features"],
        })
    return {"ok": True, "data": data}


# ── Mi suscripcion ────────────────────────────────────────────
@router.get("/mine")
async def my_subscription(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Suscripcion actual de mi empresa."""
    if not user.company_id:
        return {"ok": True, "data": None}

    result = await db.execute(
        select(Subscription).where(Subscription.company_id == user.company_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return {"ok": True, "data": None}

    plan_info = PLANS.get(sub.plan, {})
    return {
        "ok": True,
        "data": {
            "id": sub.id,
            "company_id": sub.company_id,
            "plan": sub.plan,
            "plan_label": plan_info.get("label", sub.plan),
            "state": sub.state,
            "max_users": sub.max_users,
            "max_pedidos_month": sub.max_pedidos_month,
            "price_bob": plan_info.get("price_bob", 0),
            "features": plan_info.get("features", []),
            "started_at": sub.started_at.isoformat(),
            "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
            "payment_method": sub.payment_method,
            "last_payment_date": sub.last_payment_date.isoformat() if sub.last_payment_date else None,
            "last_payment_amount": sub.last_payment_amount,
        },
    }


# ── Solicitar upgrade ─────────────────────────────────────────
class UpgradeRequest(BaseModel):
    plan: str
    notes: str | None = None


@router.post("/upgrade")
async def request_upgrade(
    body: UpgradeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Solicitar upgrade de plan (notifica al admin para billing manual)."""
    if not user.company_id:
        raise HTTPException(400, "Primero debes crear una empresa")
    if user.company_role != "company_admin":
        raise HTTPException(403, "Solo el administrador de la empresa puede solicitar upgrades")

    if body.plan not in PLANS:
        raise HTTPException(400, f"Plan invalido. Opciones: {', '.join(PLANS.keys())}")

    result = await db.execute(
        select(Subscription).where(Subscription.company_id == user.company_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(400, "No se encontro suscripcion activa")

    if sub.plan == body.plan:
        raise HTTPException(400, "Ya tienes este plan")

    # For now, just mark as pending upgrade (admin processes manually)
    sub.notes = f"UPGRADE SOLICITADO: {sub.plan} → {body.plan}. {body.notes or ''}. Solicitado por {user.full_name} ({user.email})"
    await db.commit()

    return {
        "ok": True,
        "message": f"Solicitud de upgrade a {PLANS[body.plan]['label']} registrada. Un administrador se pondra en contacto para el proceso de pago.",
    }
