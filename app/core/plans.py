"""Planes de suscripcion — cache en memoria, fuente: DB.

Al iniciar la app se llama a `load_plans_from_db()` que llena el dict `PLANS`.
Si la tabla esta vacia, se seedean los valores por defecto.
El admin puede crear/editar planes; cada cambio llama `refresh_plans_cache()`.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ── In-memory cache ───────────────────────────────────────────
PLANS: dict[str, dict] = {}

# Defaults usados para seed si la tabla esta vacia
_DEFAULT_PLANS = [
    {
        "key": "free",
        "label": "Gratuito",
        "max_users": 1,
        "max_pedidos_month": 5,
        "price_bob": 0,
        "sort_order": 1,
        "features": [
            "Cotizacion individual",
            "Hasta 5 pedidos/mes",
            "Acceso al catalogo publico",
        ],
    },
    {
        "key": "professional",
        "label": "Profesional",
        "max_users": 5,
        "max_pedidos_month": 50,
        "price_bob": 350,
        "sort_order": 2,
        "features": [
            "Equipo de hasta 5 cotizadores",
            "50 pedidos/mes",
            "Asignacion de pedidos",
            "Subida de documentos AI",
            "Soporte prioritario",
        ],
    },
    {
        "key": "enterprise",
        "label": "Empresarial",
        "max_users": 20,
        "max_pedidos_month": 999,
        "price_bob": 900,
        "sort_order": 3,
        "features": [
            "Equipo de hasta 20 usuarios",
            "Pedidos ilimitados",
            "Asignacion de pedidos",
            "Subida de documentos AI",
            "API de integracion",
            "Soporte dedicado",
        ],
    },
]


async def load_plans_from_db(db: AsyncSession) -> None:
    """Carga planes desde DB al cache. Si tabla vacia, seedea defaults."""
    from app.models.company import Plan

    result = await db.execute(
        select(Plan).where(Plan.is_active == True).order_by(Plan.sort_order)
    )
    rows = result.scalars().all()

    if not rows:
        # Seed defaults
        for p in _DEFAULT_PLANS:
            db.add(Plan(**p))
        await db.commit()
        result = await db.execute(
            select(Plan).where(Plan.is_active == True).order_by(Plan.sort_order)
        )
        rows = result.scalars().all()

    _rebuild_cache(rows)


async def refresh_plans_cache(db: AsyncSession) -> None:
    """Reconstruye el cache tras un cambio de admin."""
    from app.models.company import Plan

    result = await db.execute(
        select(Plan).where(Plan.is_active == True).order_by(Plan.sort_order)
    )
    _rebuild_cache(result.scalars().all())


def _rebuild_cache(rows) -> None:
    global PLANS
    PLANS.clear()
    for r in rows:
        PLANS[r.key] = {
            "id": r.id,
            "label": r.label,
            "max_users": r.max_users,
            "max_pedidos_month": r.max_pedidos_month,
            "price_bob": r.price_bob,
            "features": r.features or [],
            "sort_order": r.sort_order,
        }


def get_plan(plan_key: str) -> dict | None:
    return PLANS.get(plan_key)


def get_plan_limits(plan_key: str) -> tuple[int, int]:
    """Returns (max_users, max_pedidos_month) for the plan."""
    plan = PLANS.get(plan_key)
    if not plan:
        return 1, 5  # fallback free
    return plan["max_users"], plan["max_pedidos_month"]
