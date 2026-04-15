"""Planes de suscripcion para empresas."""

PLANS = {
    "free": {
        "label": "Gratuito",
        "max_users": 1,
        "max_pedidos_month": 5,
        "price_bob": 0,
        "features": [
            "Cotizacion individual",
            "Hasta 5 pedidos/mes",
            "Acceso al catalogo publico",
        ],
    },
    "professional": {
        "label": "Profesional",
        "max_users": 5,
        "max_pedidos_month": 50,
        "price_bob": 350,
        "features": [
            "Equipo de hasta 5 cotizadores",
            "50 pedidos/mes",
            "Asignacion de pedidos",
            "Subida de documentos AI",
            "Soporte prioritario",
        ],
    },
    "enterprise": {
        "label": "Empresarial",
        "max_users": 20,
        "max_pedidos_month": 999,
        "price_bob": 900,
        "features": [
            "Equipo de hasta 20 usuarios",
            "Pedidos ilimitados",
            "Asignacion de pedidos",
            "Subida de documentos AI",
            "API de integracion",
            "Soporte dedicado",
        ],
    },
}


def get_plan(plan_key: str) -> dict | None:
    return PLANS.get(plan_key)


def get_plan_limits(plan_key: str) -> tuple[int, int]:
    """Returns (max_users, max_pedidos_month) for the plan."""
    plan = PLANS.get(plan_key, PLANS["free"])
    return plan["max_users"], plan["max_pedidos_month"]
