"""Tarea: revision de suscripciones.

Marca como expiradas las suscripciones vencidas y notifica
a los admins de empresas cuya suscripcion esta por vencer.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Subscription, Company
from app.models.user import User
from app.services.notifications import notify_user

logger = logging.getLogger(__name__)

# Dias antes de expirar para enviar alerta
WARN_DAYS = 7


async def run(db: AsyncSession) -> dict:
    """Revisa suscripciones expiradas y por expirar."""
    now = datetime.now(timezone.utc)

    expired = await _mark_expired(db, now)
    warned = await _warn_expiring(db, now)

    await db.commit()
    return {
        "expired": expired,
        "warned": warned,
    }


async def _mark_expired(db: AsyncSession, now: datetime) -> int:
    """Marca como expiradas las suscripciones cuya fecha paso."""
    result = await db.execute(
        select(Subscription).where(
            Subscription.state == "active",
            Subscription.expires_at.isnot(None),
            Subscription.expires_at < now,
        )
    )
    subs = result.scalars().all()

    for sub in subs:
        sub.state = "expired"
        # Notify company admins
        admins = await _get_company_admins(db, sub.company_id)
        company = await db.get(Company, sub.company_id)
        company_name = company.name if company else "tu empresa"
        for admin in admins:
            await notify_user(
                db, admin.id,
                type="subscription_expired",
                title="Suscripcion expirada",
                body=f"La suscripcion de {company_name} ha expirado. Contacta al administrador para renovar.",
                link="company",
            )

    logger.info("Suscripciones expiradas: %d", len(subs))
    return len(subs)


async def _warn_expiring(db: AsyncSession, now: datetime) -> int:
    """Notifica sobre suscripciones que expiran pronto."""
    warn_date = now + timedelta(days=WARN_DAYS)

    result = await db.execute(
        select(Subscription).where(
            Subscription.state == "active",
            Subscription.expires_at.isnot(None),
            Subscription.expires_at > now,
            Subscription.expires_at <= warn_date,
        )
    )
    subs = result.scalars().all()

    for sub in subs:
        days_left = (sub.expires_at - now).days
        admins = await _get_company_admins(db, sub.company_id)
        company = await db.get(Company, sub.company_id)
        company_name = company.name if company else "tu empresa"
        for admin in admins:
            await notify_user(
                db, admin.id,
                type="subscription_expiring",
                title=f"Suscripcion por vencer ({days_left} dias)",
                body=f"La suscripcion de {company_name} vence en {days_left} dias. Renueva para no perder acceso.",
                link="company",
            )

    logger.info("Suscripciones por vencer (alerta): %d", len(subs))
    return len(subs)


async def _get_company_admins(db: AsyncSession, company_id: int) -> list[User]:
    """Obtiene los admins de una empresa."""
    result = await db.execute(
        select(User).where(
            User.company_id == company_id,
            User.company_role == "company_admin",
        )
    )
    return list(result.scalars().all())
