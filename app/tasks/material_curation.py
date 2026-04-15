"""Tarea: curacion automatica de materiales.

Detecta posibles duplicados en el catalogo de insumos usando
similitud de texto (pg_trgm) y sugiere agrupaciones.
"""

import logging

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.insumo import Insumo
from app.models.insumo_group import InsumoGroup

logger = logging.getLogger(__name__)


async def run(db: AsyncSession) -> dict:
    """Detecta duplicados y sugiere agrupaciones."""
    duplicates_found = await _find_duplicates(db)
    ungrouped = await _auto_group_ungrouped(db)

    await db.commit()
    return {
        "duplicates_found": duplicates_found,
        "auto_grouped": ungrouped,
    }


async def _find_duplicates(db: AsyncSession) -> int:
    """Encuentra pares de insumos con nombre muy similar (>0.6 similaridad)."""
    # Use pg_trgm similarity to find potential duplicates
    query = text("""
        SELECT a.id AS id_a, b.id AS id_b,
               a.name AS name_a, b.name AS name_b,
               similarity(a.name_normalized, b.name_normalized) AS sim
        FROM mkt_insumo a
        JOIN mkt_insumo b ON a.id < b.id
        WHERE a.is_active = true AND b.is_active = true
          AND a.uom_normalized = b.uom_normalized
          AND similarity(a.name_normalized, b.name_normalized) > 0.6
          AND a.group_id IS DISTINCT FROM b.group_id
        ORDER BY sim DESC
        LIMIT 50
    """)

    try:
        result = await db.execute(query)
        pairs = result.all()
    except Exception as e:
        logger.warning("Error buscando duplicados (pg_trgm): %s", e)
        return 0

    # Auto-group pairs with very high similarity (>0.85)
    grouped = 0
    for pair in pairs:
        if pair.sim >= 0.85:
            a = await db.get(Insumo, pair.id_a)
            b = await db.get(Insumo, pair.id_b)
            if not a or not b:
                continue

            if a.group_id and not b.group_id:
                b.group_id = a.group_id
                grouped += 1
            elif b.group_id and not a.group_id:
                a.group_id = b.group_id
                grouped += 1
            elif not a.group_id and not b.group_id:
                # Create a new group
                group = InsumoGroup(
                    name=a.name,
                    category=a.category,
                    uom=a.uom,
                )
                db.add(group)
                await db.flush()
                a.group_id = group.id
                b.group_id = group.id
                grouped += 2

    logger.info("Duplicados encontrados: %d pares, auto-agrupados: %d", len(pairs), grouped)
    return len(pairs)


async def _auto_group_ungrouped(db: AsyncSession) -> int:
    """Agrupa insumos sin grupo que comparten categoria + nombre similar."""
    # Count ungrouped insumos
    count_q = select(func.count(Insumo.id)).where(
        Insumo.group_id.is_(None),
        Insumo.is_active == True,  # noqa: E712
    )
    ungrouped_count = (await db.execute(count_q)).scalar() or 0

    if ungrouped_count == 0:
        return 0

    # Try to match ungrouped insumos to existing groups by name similarity
    query = text("""
        SELECT i.id AS insumo_id, g.id AS group_id,
               similarity(i.name_normalized, g.name) AS sim
        FROM mkt_insumo i
        CROSS JOIN LATERAL (
            SELECT ig.id, ig.name
            FROM mkt_insumo_group ig
            WHERE ig.category = i.category
              AND similarity(i.name_normalized, ig.name) > 0.5
            ORDER BY similarity(i.name_normalized, ig.name) DESC
            LIMIT 1
        ) g
        WHERE i.group_id IS NULL AND i.is_active = true
        LIMIT 100
    """)

    try:
        result = await db.execute(query)
        matches = result.all()
    except Exception as e:
        logger.warning("Error auto-agrupando: %s", e)
        return 0

    assigned = 0
    for m in matches:
        if m.sim >= 0.6:
            insumo = await db.get(Insumo, m.insumo_id)
            if insumo and not insumo.group_id:
                insumo.group_id = m.group_id
                assigned += 1

    logger.info("Auto-agrupados %d insumos en grupos existentes", assigned)
    return assigned
