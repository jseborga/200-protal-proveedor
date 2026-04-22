"""Tarea: auto-handoff por timeout SLA breach (Fase 5.10).

Detecta sesiones de inbox asignadas donde el operador no respondio
dentro de `threshold_hours` despues del ultimo mensaje del cliente
y las reasigna a otro operador on-duty (o las libera al pool si no
hay candidato).

Config en `mkt_system_setting[inbox_sla_handoff]`:
  - enabled: bool (default False)
  - threshold_hours: int 1-72 (default 4)

Cooldown anti-ping-pong: >= `threshold_hours` via
`ConversationSession.last_handoff_at`.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inbox_sla_handoff import (
    find_breached_sessions,
    get_handoff_config,
    handoff_session,
)

logger = logging.getLogger(__name__)


async def run(db: AsyncSession) -> dict:
    """Ejecuta un ciclo de handoff. Devuelve stats para el TaskLog."""
    cfg = await get_handoff_config(db)
    if not cfg["enabled"]:
        return {
            "skipped": "disabled",
            "checked": 0,
            "handoffs": 0,
            "released": 0,
        }

    threshold_hours = int(cfg["threshold_hours"])
    now = datetime.now(timezone.utc)

    sessions = await find_breached_sessions(db, now, threshold_hours)
    checked = len(sessions)

    handoffs = 0
    released = 0
    for sess in sessions:
        try:
            result = await handoff_session(db, sess, now=now)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Handoff fallo en session %s: %s", sess.id, exc)
            continue
        if result == "reassigned":
            handoffs += 1
        elif result == "released":
            released += 1

    await db.commit()
    return {
        "threshold_hours": threshold_hours,
        "checked": checked,
        "handoffs": handoffs,
        "released": released,
    }
