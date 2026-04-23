"""Tarea: auto-handoff por timeout SLA breach (Fase 5.10).

Detecta sesiones de inbox asignadas donde el operador no respondio
dentro de `threshold_hours` despues del ultimo mensaje del cliente
y las reasigna a otro operador on-duty. Si no hay candidato, la
sesion queda intacta (el proximo tick reintentara).

Config en `mkt_system_setting[inbox_sla]`:
  - sla_hours: int 1-72 (default 4, compartido con /metrics)
  - handoff_enabled: bool (default False)

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
            "noop": 0,
        }

    threshold_hours = int(cfg["threshold_hours"])
    now = datetime.now(timezone.utc)

    sessions = await find_breached_sessions(db, now, threshold_hours)
    checked = len(sessions)

    handoffs = 0
    noop = 0
    # Capturamos (session_id, prev_op, new_op) para emitir WS post-commit.
    reassignments: list[tuple[int, int | None, int | None]] = []
    for sess in sessions:
        prev_op = sess.operator_id
        try:
            result = await handoff_session(db, sess, now=now)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Handoff fallo en session %s: %s", sess.id, exc)
            continue
        if result == "reassigned":
            handoffs += 1
            reassignments.append((sess.id, prev_op, sess.operator_id))
        else:
            noop += 1

    await db.commit()

    # 5.11: WS live updates post-commit. Errores aqui no deben romper el cron.
    if reassignments:
        try:
            from app.services.inbox_autoassign import get_config as _aa_get_config
            from app.services.inbox_ws import (
                publish_session_operator_changed as _ws_op_changed,
            )
            try:
                _aa_cfg = await _aa_get_config(db)
                strategy = _aa_cfg.get("strategy")
            except Exception:  # noqa: BLE001
                strategy = None
            for sess_id, prev_op, new_op in reassignments:
                await _ws_op_changed(
                    session_id=sess_id,
                    prev_operator_id=prev_op,
                    operator_id=new_op,
                    reason="auto_handoff",
                    strategy=strategy,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("inbox_ws publish (handoff) error: %s", exc)

    return {
        "threshold_hours": threshold_hours,
        "checked": checked,
        "handoffs": handoffs,
        "noop": noop,
    }
