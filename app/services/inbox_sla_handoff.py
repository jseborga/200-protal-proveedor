"""Auto-handoff por timeout SLA breach (Fase 5.10).

Cuando una sesion asignada lleva demasiado tiempo sin respuesta del
operador (y el cliente escribio despues), un cron periodico (`inbox_sla_handoff`)
la reasigna a otro operador on-duty. Si no hay candidato, la libera al
pool (operator_id=None).

Config persistida en `mkt_system_setting` con key `inbox_sla_handoff`:
    {
        "enabled": bool,
        "threshold_hours": int (1-72),
    }

El cooldown anti-ping-pong usa `ConversationSession.last_handoff_at`
(columna agregada en migracion 0004).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes as sa_attrs

from app.models.conversation import ConversationSession, Message
from app.models.system_setting import SystemSetting
from app.models.user import User

logger = logging.getLogger(__name__)

SETTING_KEY = "inbox_sla_handoff"

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "threshold_hours": 4,
}

MIN_THRESHOLD_HOURS = 1
MAX_THRESHOLD_HOURS = 72


def _normalize(cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Coerciona claves faltantes a defaults y clampea threshold."""
    base = {**DEFAULT_CONFIG}
    if cfg:
        if "enabled" in cfg:
            base["enabled"] = bool(cfg["enabled"])
        if "threshold_hours" in cfg:
            try:
                v = int(cfg["threshold_hours"])
            except (TypeError, ValueError):
                v = DEFAULT_CONFIG["threshold_hours"]
            base["threshold_hours"] = max(MIN_THRESHOLD_HOURS, min(MAX_THRESHOLD_HOURS, v))
    return base


async def get_handoff_config(db: AsyncSession) -> dict[str, Any]:
    """Lee la config o devuelve defaults si no existe."""
    setting = await db.get(SystemSetting, SETTING_KEY)
    return _normalize(setting.value if setting else None)


async def save_handoff_config(db: AsyncSession, cfg: dict[str, Any]) -> dict[str, Any]:
    """Upsert con normalizacion. Devuelve la config guardada."""
    normalized = _normalize(cfg)
    setting = await db.get(SystemSetting, SETTING_KEY)
    if setting:
        setting.value = normalized
        sa_attrs.flag_modified(setting, "value")
    else:
        setting = SystemSetting(key=SETTING_KEY, value=normalized)
        db.add(setting)
    await db.commit()
    return normalized


async def find_breached_sessions(
    db: AsyncSession, now: datetime, threshold_hours: int
) -> list[ConversationSession]:
    """Sesiones candidatas a handoff segun criterio SLA + cooldown.

    Reusa el criterio del endpoint `/metrics` (inbox.py):
      - state != "closed"
      - operator_id IS NOT NULL
      - last_client_msg_at < now - threshold
      - operador no leyo despues del ultimo mensaje del cliente
      - operador no respondio despues del ultimo mensaje del cliente
      - cooldown anti-ping-pong >= threshold
    """
    cutoff = now - timedelta(hours=threshold_hours)
    cooldown_cutoff = now - timedelta(hours=threshold_hours)
    stmt = (
        select(ConversationSession)
        .where(
            ConversationSession.state != "closed",
            ConversationSession.operator_id.is_not(None),
            ConversationSession.last_client_msg_at.is_not(None),
            ConversationSession.last_client_msg_at < cutoff,
            or_(
                ConversationSession.operator_last_read_at.is_(None),
                ConversationSession.last_client_msg_at
                > ConversationSession.operator_last_read_at,
            ),
            or_(
                ConversationSession.last_operator_msg_at.is_(None),
                ConversationSession.last_client_msg_at
                > ConversationSession.last_operator_msg_at,
            ),
            or_(
                ConversationSession.last_handoff_at.is_(None),
                ConversationSession.last_handoff_at < cooldown_cutoff,
            ),
        )
        .order_by(ConversationSession.last_client_msg_at.asc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def handoff_session(
    db: AsyncSession,
    session: ConversationSession,
    *,
    now: datetime | None = None,
) -> Literal["reassigned", "released", "noop"]:
    """Intenta reasignar a otro on-duty; si no hay, libera al pool.

    - Persiste `last_handoff_at = now`.
    - Agrega Message sistema al timeline.
    - Dispara push al nuevo operador (si hubo reasignacion).
    - NO commitea; el caller debe comitear.

    Devuelve:
      - "reassigned" si operator_id cambio a otro usuario on-duty.
      - "released"   si no hubo candidato y operator_id quedo en None.
      - "noop"       si no se pudo hacer nada (ej: sesion ya sin operador).
    """
    from app.services.inbox_autoassign import get_config, pick_next_operator

    if now is None:
        now = datetime.now(timezone.utc)

    previous_id = session.operator_id
    if previous_id is None:
        return "noop"

    cfg = await get_config(db)
    new_op = await pick_next_operator(db, cfg, exclude_user_id=previous_id)

    session.last_handoff_at = now

    if new_op is not None:
        session.operator_id = new_op.id
        strategy = cfg.get("strategy", "round_robin")
        db.add(
            Message(
                session_id=session.id,
                direction="internal",
                channel="web",
                sender_type="system",
                body=(
                    f"Reasignado por timeout SLA a "
                    f"{new_op.full_name or new_op.email} ({strategy})."
                ),
            )
        )
        # Actualizar cursor round-robin para consistencia con auto-assign.
        try:
            from app.services.inbox_autoassign import save_config as _save_aa_config
            cfg["last_assigned_user_id"] = new_op.id
            await _save_aa_config(db, cfg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo actualizar cursor round-robin: %s", exc)

        # Push al nuevo operador (best-effort).
        try:
            from app.services.webpush import send_push_to_user

            await send_push_to_user(
                db,
                new_op.id,
                {
                    "title": "Nueva conversacion reasignada",
                    "body": (
                        f"Sesion #{session.id} reasignada por timeout SLA."
                    ),
                    "url": f"/inbox/{session.id}",
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fallo push handoff a user %s: %s", new_op.id, exc)

        return "reassigned"

    # No hay candidato on-duty -> liberar al pool.
    session.operator_id = None
    db.add(
        Message(
            session_id=session.id,
            direction="internal",
            channel="web",
            sender_type="system",
            body="Liberado al pool por timeout SLA (sin operadores on-duty).",
        )
    )
    return "released"
