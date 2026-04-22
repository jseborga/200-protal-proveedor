"""Auto-asignacion de operadores a nuevas conversaciones del Inbox (Fase 5.7).

Se dispara al primer mensaje inbound del cliente en `messaging.py` via
`auto_assign_if_needed`. Si la config esta activa y la sesion no tiene
operator_id, elige un operador con estrategia round_robin o least_loaded
y lo asigna, dejando un `Message` de sistema para dejar rastro.

Config persistida en `mkt_system_setting` con key `inbox_autoassign`:
    {
        "enabled": bool,
        "strategy": "round_robin" | "least_loaded",
        "pool_user_ids": list[int],          # [] = todos los staff activos
        "last_assigned_user_id": int | None, # cursor round-robin
    }
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes as sa_attrs

from app.api.deps import STAFF_ROLES
from app.models.conversation import ConversationSession, Message
from app.models.system_setting import SystemSetting
from app.models.user import User

SETTING_KEY = "inbox_autoassign"

VALID_STRATEGIES = ("round_robin", "least_loaded")

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "strategy": "round_robin",
    "pool_user_ids": [],
    "last_assigned_user_id": None,
}


def _normalize(cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Coerciona claves faltantes a defaults y valida strategy."""
    base = {**DEFAULT_CONFIG}
    if cfg:
        if "enabled" in cfg:
            base["enabled"] = bool(cfg["enabled"])
        if "strategy" in cfg and cfg["strategy"] in VALID_STRATEGIES:
            base["strategy"] = cfg["strategy"]
        if "pool_user_ids" in cfg and isinstance(cfg["pool_user_ids"], list):
            base["pool_user_ids"] = [int(x) for x in cfg["pool_user_ids"] if isinstance(x, int) or str(x).isdigit()]
        if "last_assigned_user_id" in cfg:
            v = cfg["last_assigned_user_id"]
            base["last_assigned_user_id"] = int(v) if v is not None else None
    return base


async def get_config(db: AsyncSession) -> dict[str, Any]:
    """Lee la config o devuelve defaults si no existe."""
    setting = await db.get(SystemSetting, SETTING_KEY)
    return _normalize(setting.value if setting else None)


async def save_config(db: AsyncSession, cfg: dict[str, Any]) -> dict[str, Any]:
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


async def _get_eligible_operators(
    db: AsyncSession, pool_user_ids: list[int]
) -> list[User]:
    """Staff activo. Si pool vacio -> todos los STAFF_ROLES con is_active.

    Fase 5.8: filtra por horario on-duty via
    `operator_availability.filter_on_duty` (operadores sin schedule
    definido pasan siempre).
    """
    from app.services.operator_availability import filter_on_duty

    stmt = select(User).where(
        User.role.in_(STAFF_ROLES),
        User.is_active.is_(True),
    )
    if pool_user_ids:
        stmt = stmt.where(User.id.in_(pool_user_ids))
    stmt = stmt.order_by(User.id)
    users = list((await db.execute(stmt)).scalars().all())
    return await filter_on_duty(db, users)


def _pick_round_robin(
    eligible: list[User], last_id: int | None
) -> User | None:
    """Siguiente despues de last_id en eligible (ya ordenado por id asc)."""
    if not eligible:
        return None
    if last_id is None:
        return eligible[0]
    for u in eligible:
        if u.id > last_id:
            return u
    # wrap around
    return eligible[0]


async def _pick_least_loaded(
    db: AsyncSession, eligible: list[User]
) -> User | None:
    """Operador con menor cantidad de sesiones abiertas.

    Desempate por user_id asc (ya ordenado por eligible).
    """
    if not eligible:
        return None
    ids = [u.id for u in eligible]
    stmt = (
        select(
            ConversationSession.operator_id,
            func.count(ConversationSession.id).label("n"),
        )
        .where(
            ConversationSession.state != "closed",
            ConversationSession.operator_id.in_(ids),
        )
        .group_by(ConversationSession.operator_id)
    )
    counts = {r.operator_id: int(r.n) for r in (await db.execute(stmt)).all()}
    # pick el de menor count; eligible ya viene ordenado por id asc -> estable
    best: User | None = None
    best_count = -1
    for u in eligible:
        c = counts.get(u.id, 0)
        if best is None or c < best_count:
            best = u
            best_count = c
    return best


async def auto_assign_if_needed(
    db: AsyncSession, session: ConversationSession
) -> User | None:
    """Si esta habilitado y la sesion no tiene operador, asigna uno.

    - No commitea la sesion por si misma (deja que el caller haga commit
      al final del flujo), pero si persiste el nuevo cursor en config.
    - Inserta un `Message` de sistema para dejar rastro en el timeline.
    - No lanza: los errores se capturan arriba (messaging.py).

    Devuelve el User asignado, o None si no se asigno.
    """
    if session.operator_id:
        return None

    cfg = await get_config(db)
    if not cfg["enabled"]:
        return None

    eligible = await _get_eligible_operators(db, cfg["pool_user_ids"])
    if not eligible:
        return None

    picked: User | None = None
    strategy = cfg["strategy"]
    if strategy == "least_loaded":
        picked = await _pick_least_loaded(db, eligible)
    else:
        picked = _pick_round_robin(eligible, cfg.get("last_assigned_user_id"))

    if picked is None:
        return None

    session.operator_id = picked.id

    # Rastro en el timeline como nota de sistema (no propaga a WA/TG).
    db.add(
        Message(
            session_id=session.id,
            direction="internal",
            channel="web",
            sender_type="system",
            body=f"Auto-asignado a {picked.full_name or picked.email} ({strategy}).",
        )
    )

    # Actualizar cursor round-robin (tambien en least_loaded, por simetria).
    cfg["last_assigned_user_id"] = picked.id
    await save_config(db, cfg)

    return picked
