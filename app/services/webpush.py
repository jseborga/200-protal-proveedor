"""Envio de Web Push notifications (VAPID).

Usa `pywebpush` para entregar payloads a endpoints (FCM/Mozilla/etc). Las
suscripciones se guardan en `mkt_push_subscription`. Si el endpoint responde
404/410 borramos la suscripcion (expiro).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.push_subscription import PushSubscription

logger = logging.getLogger("webpush")


def _vapid_configured() -> bool:
    return bool(settings.vapid_private_key and settings.vapid_public_key)


async def send_push_to_user(
    db: AsyncSession,
    user_id: int,
    payload: dict[str, Any],
) -> int:
    """Envia un push a todas las suscripciones activas de `user_id`.

    Devuelve la cantidad de pushes entregados con exito. Limpia suscripciones
    expiradas (404/410). Cualquier otro fallo se loguea pero no interrumpe.
    """
    if not _vapid_configured():
        logger.debug("[webpush] VAPID no configurado, skip")
        return 0

    try:
        from pywebpush import WebPushException, webpush
    except Exception as e:
        logger.warning("[webpush] pywebpush no instalado: %s", e)
        return 0

    rows = (await db.execute(
        select(PushSubscription).where(PushSubscription.user_id == user_id)
    )).scalars().all()
    if not rows:
        return 0

    data = json.dumps(payload, ensure_ascii=False, default=str)
    vapid_claims = {"sub": settings.vapid_subject or "mailto:admin@localhost"}
    delivered = 0
    to_delete: list[int] = []

    for sub in rows:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=data,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims=dict(vapid_claims),
                ttl=60,
            )
            delivered += 1
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                # endpoint expirado -> borrar
                to_delete.append(sub.id)
            else:
                logger.warning(
                    "[webpush] fallo envio user=%s status=%s err=%s",
                    user_id, status, e,
                )
        except Exception as e:  # noqa: BLE001
            logger.exception("[webpush] error inesperado: %s", e)

    if to_delete:
        for sub in rows:
            if sub.id in to_delete:
                await db.delete(sub)
        try:
            await db.commit()
        except Exception:
            await db.rollback()

    return delivered
