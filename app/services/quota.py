"""Estado de suscripcion y aplicacion de cuotas.

Los cobros son manuales, asi que el control real lo hacen las FECHAS: una
suscripcion vale mientras no venza (o mientras dure su prueba gratuita). Al
vencer no se bloquea el acceso de golpe — eso hace perder clientes y datos —
sino que se degrada a los limites del plan gratuito tras un periodo de gracia.
Lo que ya existe se conserva y se puede leer; lo que se corta es CREAR mas.

Estados efectivos:
    trial    prueba gratuita vigente        -> limites del plan
    active   vigente (o sin vencimiento)    -> limites del plan
    grace    vencida hace poco              -> limites del plan + aviso
    expired  vencida y pasada la gracia     -> limites del plan gratuito
    suspended/cancelled  (fijado a mano)    -> limites del plan gratuito
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Limites de respaldo si no hay plan gratuito configurado en la base.
FALLBACK_FREE_LIMITS = {"max_users": 1, "max_projects": 1, "max_pedidos_month": 5}

# 402 Payment Required: el frontend lo usa para ofrecer la mejora de plan.
QUOTA_STATUS = status.HTTP_402_PAYMENT_REQUIRED


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def resolve_state(subscription, now: datetime | None = None) -> str:
    """Estado efectivo de la suscripcion segun las fechas."""
    if subscription is None:
        return "expired"

    now = now or datetime.now(timezone.utc)

    # Estados fijados a mano por un admin mandan sobre las fechas.
    if subscription.state in ("suspended", "cancelled"):
        return subscription.state

    trial_ends = _as_utc(getattr(subscription, "trial_ends_at", None))
    if trial_ends and trial_ends > now:
        return "trial"

    expires = _as_utc(subscription.expires_at)
    if expires is None:
        return "active"  # sin vencimiento (plan gratuito de por vida)
    if expires > now:
        return "active"

    grace_days = getattr(subscription, "grace_days", 0) or 0
    if now <= expires + timedelta(days=grace_days):
        return "grace"
    return "expired"


def has_full_limits(state: str) -> bool:
    return state in ("trial", "active", "grace")


def get_effective_limits(subscription, state: str | None = None) -> dict:
    """Limites que aplican AHORA a la empresa."""
    from app.core.plans import get_plan

    state = state or resolve_state(subscription)

    if subscription is not None and has_full_limits(state):
        return {
            "max_users": subscription.max_users,
            "max_projects": getattr(subscription, "max_projects", 1),
            "max_pedidos_month": subscription.max_pedidos_month,
        }

    free = get_plan("free")
    if not free:
        return dict(FALLBACK_FREE_LIMITS)
    return {
        "max_users": free.get("max_users", 1),
        "max_projects": free.get("max_projects", 1),
        "max_pedidos_month": free.get("max_pedidos_month", 5),
    }


async def get_subscription(db: AsyncSession, company_id: int):
    from app.models.company import Subscription

    result = await db.execute(
        select(Subscription).where(Subscription.company_id == company_id)
    )
    return result.scalar_one_or_none()


async def describe(db: AsyncSession, company_id: int) -> dict:
    """Resumen de estado + limites + consumo, para mostrar en la UI."""
    from app.models.apu import ApuProject
    from app.models.user import User

    sub = await get_subscription(db, company_id)
    state = resolve_state(sub)
    limits = get_effective_limits(sub, state)

    users_used = (await db.execute(
        select(func.count(User.id)).where(User.company_id == company_id)
    )).scalar() or 0
    projects_used = (await db.execute(
        select(func.count(ApuProject.id)).where(
            ApuProject.company_id == company_id, ApuProject.is_active == True,  # noqa: E712
        )
    )).scalar() or 0

    return {
        "plan": sub.plan if sub else "free",
        "state": state,
        "expires_at": sub.expires_at.isoformat() if sub and sub.expires_at else None,
        "trial_ends_at": (
            sub.trial_ends_at.isoformat()
            if sub and getattr(sub, "trial_ends_at", None) else None
        ),
        "limits": limits,
        "usage": {"users": users_used, "projects": projects_used},
        "can_create_project": projects_used < limits["max_projects"],
        "can_add_user": users_used < limits["max_users"],
    }


async def assert_can_create_project(db: AsyncSession, company_id: int) -> None:
    """Corta la creacion de un proyecto si se alcanzo el limite del plan."""
    from app.models.apu import ApuProject

    sub = await get_subscription(db, company_id)
    state = resolve_state(sub)
    limits = get_effective_limits(sub, state)

    used = (await db.execute(
        select(func.count(ApuProject.id)).where(
            ApuProject.company_id == company_id, ApuProject.is_active == True,  # noqa: E712
        )
    )).scalar() or 0

    if used >= limits["max_projects"]:
        if state == "expired":
            detail = (
                f"Tu suscripcion vencio y volviste al limite gratuito de "
                f"{limits['max_projects']} proyecto(s). Renueva para recuperar tu plan."
            )
        else:
            detail = (
                f"Alcanzaste el limite de {limits['max_projects']} proyecto(s) "
                f"de tu plan. Mejora tu plan para crear mas."
            )
        raise HTTPException(status_code=QUOTA_STATUS, detail=detail)


async def assert_can_add_user(db: AsyncSession, company_id: int) -> None:
    """Corta el alta de un miembro si se alcanzo el limite de asientos."""
    from app.models.user import User

    sub = await get_subscription(db, company_id)
    state = resolve_state(sub)
    limits = get_effective_limits(sub, state)

    used = (await db.execute(
        select(func.count(User.id)).where(User.company_id == company_id)
    )).scalar() or 0

    if used >= limits["max_users"]:
        raise HTTPException(
            status_code=QUOTA_STATUS,
            detail=(
                f"Alcanzaste el limite de {limits['max_users']} usuario(s) de tu "
                f"plan. Mejora tu plan para sumar mas."
            ),
        )


def compute_period_end(start: datetime, months: int) -> datetime:
    """Fin de periodo sumando meses de calendario, sin dependencias extra."""
    months = max(1, int(months or 1))
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    # Ajuste de fin de mes: 31 de enero + 1 mes = 28/29 de febrero.
    day = start.day
    while day > 28:
        try:
            return start.replace(year=year, month=month, day=day)
        except ValueError:
            day -= 1
    return start.replace(year=year, month=month, day=day)


def apply_discount(price: float, subscription, today=None) -> float:
    """Precio con el bono de descuento vigente aplicado."""
    if subscription is None:
        return price
    pct = getattr(subscription, "discount_pct", 0.0) or 0.0
    if pct <= 0:
        return price
    until = getattr(subscription, "discount_until", None)
    if until is not None:
        today = today or datetime.now(timezone.utc).date()
        if until < today:
            return price
    return round(price * (1 - min(pct, 100.0) / 100.0), 2)
