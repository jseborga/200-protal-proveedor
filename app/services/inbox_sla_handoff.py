"""Auto-handoff por timeout SLA breach (Fase 5.10).

Cuando una sesion asignada lleva demasiado tiempo sin respuesta del
operador (y el cliente escribio despues), un cron periodico (`inbox_sla_handoff`)
la reasigna a otro operador on-duty. Si no hay candidato disponible,
la sesion se deja intacta (asignada al operador actual) y se vuelve a
intentar en el siguiente tick.

Config compartida con /metrics en `mkt_system_setting` key `inbox_sla`:
    {
        "sla_hours": int (1-72),   # umbral SLA unico, default 4
        "handoff_enabled": bool,   # activa el auto-handoff
    }

El cooldown anti-ping-pong usa `ConversationSession.last_handoff_at`
(columna agregada en migracion 0004). Solo se actualiza cuando
efectivamente se reasigna.
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

logger = logging.getLogger(__name__)

SETTING_KEY = "inbox_sla"
LEGACY_SETTING_KEY = "inbox_sla_handoff"  # Fase 5.10 inicial (pre-correccion)

DEFAULT_SLA_HOURS = 4
MIN_THRESHOLD_HOURS = 1
MAX_THRESHOLD_HOURS = 72

DEFAULT_SHARED_CONFIG: dict[str, Any] = {
    "sla_hours": DEFAULT_SLA_HOURS,
    "handoff_enabled": False,
}


def _clamp_hours(v: Any) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return DEFAULT_SLA_HOURS
    return max(MIN_THRESHOLD_HOURS, min(MAX_THRESHOLD_HOURS, n))


def _normalize_shared(cfg: dict[str, Any] | None) -> dict[str, Any]:
    base = {**DEFAULT_SHARED_CONFIG}
    if cfg:
        if "sla_hours" in cfg:
            base["sla_hours"] = _clamp_hours(cfg["sla_hours"])
        if "handoff_enabled" in cfg:
            base["handoff_enabled"] = bool(cfg["handoff_enabled"])
    return base


async def _get_shared_config(db: AsyncSession) -> dict[str, Any]:
    """Lee la config unificada. Migra silenciosamente la key vieja si existe.

    Si la tabla `mkt_system_setting` no existe (entornos minimos de test),
    devuelve defaults sin fallar.
    """
    try:
        setting = await db.get(SystemSetting, SETTING_KEY)
    except Exception:  # noqa: BLE001  (tabla ausente u otro error de DB)
        await db.rollback()
        return {**DEFAULT_SHARED_CONFIG}
    if setting is None:
        # Migracion silenciosa desde la key antigua (Fase 5.10 pre-correccion)
        legacy = await db.get(SystemSetting, LEGACY_SETTING_KEY)
        if legacy and isinstance(legacy.value, dict):
            migrated = {
                "sla_hours": _clamp_hours(legacy.value.get("threshold_hours")),
                "handoff_enabled": bool(legacy.value.get("enabled", False)),
            }
            db.add(SystemSetting(key=SETTING_KEY, value=migrated))
            await db.commit()
            return migrated
        return {**DEFAULT_SHARED_CONFIG}
    return _normalize_shared(setting.value)


async def _save_shared_config(
    db: AsyncSession, cfg: dict[str, Any]
) -> dict[str, Any]:
    normalized = _normalize_shared(cfg)
    setting = await db.get(SystemSetting, SETTING_KEY)
    if setting:
        setting.value = normalized
        sa_attrs.flag_modified(setting, "value")
    else:
        setting = SystemSetting(key=SETTING_KEY, value=normalized)
        db.add(setting)
    await db.commit()
    return normalized


# ── API publica: handoff config (compat con endpoints de admin) ──

async def get_handoff_config(db: AsyncSession) -> dict[str, Any]:
    """Devuelve la config del auto-handoff en shape estable.

    Shape: `{"enabled": bool, "threshold_hours": int}`.
    Internamente mapea desde la key compartida `inbox_sla`.
    """
    shared = await _get_shared_config(db)
    return {
        "enabled": bool(shared["handoff_enabled"]),
        "threshold_hours": int(shared["sla_hours"]),
    }


async def save_handoff_config(
    db: AsyncSession, cfg: dict[str, Any]
) -> dict[str, Any]:
    """Guarda `enabled` y `threshold_hours` en la key compartida.

    Preserva otros campos si los hubiera (por ahora solo esos dos).
    """
    current = await _get_shared_config(db)
    updated = {
        "sla_hours": _clamp_hours(cfg.get("threshold_hours", current["sla_hours"])),
        "handoff_enabled": bool(cfg.get("enabled", current["handoff_enabled"])),
    }
    saved = await _save_shared_config(db, updated)
    return {
        "enabled": bool(saved["handoff_enabled"]),
        "threshold_hours": int(saved["sla_hours"]),
    }


async def get_sla_default_hours(db: AsyncSession) -> int:
    """Default compartido de `sla_hours` para `/metrics`."""
    shared = await _get_shared_config(db)
    return int(shared["sla_hours"])


# ── Criterio de breach + handoff action ──────────────────────────

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
) -> Literal["reassigned", "noop"]:
    """Intenta reasignar a otro operador on-duty.

    Comportamiento (Fase 5.10 corregida):
    - Si hay candidato on-duty distinto al actual: reasigna, persiste
      `last_handoff_at = now`, agrega Message sistema, dispara push
      best-effort al nuevo operador. Devuelve "reassigned".
    - Si NO hay candidato: deja la sesion intacta (no libera al pool,
      no toca `last_handoff_at`). Devuelve "noop".
    - Si la sesion no tiene operador actual: "noop" sin cambios.

    NO commitea (caller comitea).
    """
    from app.services.inbox_autoassign import (
        get_config as _get_aa_config,
        pick_next_operator,
        save_config as _save_aa_config,
    )

    if now is None:
        now = datetime.now(timezone.utc)

    previous_id = session.operator_id
    if previous_id is None:
        return "noop"

    cfg = await _get_aa_config(db)
    new_op = await pick_next_operator(db, cfg, exclude_user_id=previous_id)

    if new_op is None:
        # Sin candidato: no mover nada. El proximo tick reintentara.
        return "noop"

    session.operator_id = new_op.id
    session.last_handoff_at = now
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
    # Cursor round-robin consistente con auto-assign (best-effort).
    try:
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
                "body": f"Sesion #{session.id} reasignada por timeout SLA.",
                "url": f"/inbox/{session.id}",
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fallo push handoff a user %s: %s", new_op.id, exc)

    return "reassigned"
