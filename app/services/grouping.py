"""Logica de agrupacion de insumos por familia/variantes."""

import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.insumo import Insumo
from app.services.matching import normalize_text

# Colores comunes en nombres de productos de construccion
_COLORS = {
    "rojo", "verde", "azul", "blanco", "negro", "amarillo", "gris",
    "naranja", "marron", "cafe", "beige", "crema", "celeste", "rosado",
    "dorado", "plateado", "turquesa", "salmon", "marfil", "terracota",
    "ocre", "lila", "violeta", "colonial", "bosque", "arena", "hueso",
    "ivory", "chocolate", "caoba", "camel", "piedra",
}

# Patrones de dimensiones/medidas a extraer del nombre
_DIM_PATTERNS = [
    # Medidas con unidad: "10mm", "3/4 pulg", "0.9 l", "1/2\"", "4x8x20"
    r"\d+[\./]\d+\s*(?:mm|cm|m|pulg|pulgadas?|plg)\b",
    r"\d+(?:\.\d+)?\s*(?:mm|cm|m|pulg|pulgadas?|plg|kg|kgs?|l|lt|lts?|gl|gal|galon|galones)\b",
    r'\d+(?:\.\d+)?\s*"',
    # Dimensiones compuestas: "12x8x25", "4x8"
    r"\d+\s*x\s*\d+(?:\s*x\s*\d+)*",
    # Fracciones solas: "1/2", "3/4" (comunes en tuberias)
    r"\b\d+/\d+\b",
    # Numeros sueltos al final (diametros, calibres): "calibre 12", "no 8"
    r"\b(?:no|n|calibre|cal|diam|diametro)\s*\.?\s*\d+(?:\.\d+)?\b",
]


def extract_base_name(name: str) -> str:
    """Extrae el nombre base de un producto quitando dimensiones, colores y medidas."""
    text = normalize_text(name)

    # Quitar patrones de dimension
    for pattern in _DIM_PATTERNS:
        text = re.sub(pattern, " ", text)

    # Quitar colores
    words = text.split()
    words = [w for w in words if w not in _COLORS]
    text = " ".join(words)

    # Limpiar espacios resultantes
    text = re.sub(r"\s+", " ", text).strip()

    return text


async def suggest_groups(
    db: AsyncSession,
    category: str | None = None,
    min_members: int = 2,
) -> list[dict]:
    """Sugiere agrupaciones de insumos por similitud de nombre base."""
    query = select(Insumo).where(
        Insumo.is_active == True,
        Insumo.group_id.is_(None),
    )
    if category:
        query = query.where(Insumo.category == category)

    result = await db.execute(query.order_by(Insumo.name))
    insumos = result.scalars().all()

    # Agrupar por (category, base_name)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for ins in insumos:
        base = extract_base_name(ins.name)
        if not base or len(base) < 3:
            continue
        key = (ins.category or "", base)
        groups[key].append({
            "id": ins.id,
            "name": ins.name,
            "uom": ins.uom,
            "ref_price": ins.ref_price,
        })

    # Filtrar y ordenar
    suggestions = []
    for (cat, base), members in groups.items():
        if len(members) < min_members:
            continue
        prices = [m["ref_price"] for m in members if m["ref_price"] is not None]
        suggestions.append({
            "suggested_name": base.title(),
            "category": cat or None,
            "member_count": len(members),
            "price_range": {
                "min": min(prices) if prices else None,
                "max": max(prices) if prices else None,
            },
            "insumos": members,
        })

    suggestions.sort(key=lambda x: x["member_count"], reverse=True)
    return suggestions
