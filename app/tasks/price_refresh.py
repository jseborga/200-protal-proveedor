"""Tarea: recalcular precios de referencia de insumos.

Ejecuta bulk_update_prices de pricing.py para todas las regiones
y tambien recalcula precios desde pedidos completados.
"""

import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.insumo import Insumo
from app.models.pedido import PedidoPrecio, PedidoItem, Pedido
from app.services.pricing import bulk_update_prices

logger = logging.getLogger(__name__)


async def run(db: AsyncSession) -> dict:
    """Recalcula precios de referencia para todos los insumos."""
    # 1. Bulk update from quotation lines (existing logic)
    result = await bulk_update_prices(db)
    logger.info("Precios actualizados desde cotizaciones: %s", result)

    # 2. Update from pedido precios (selected prices from completed pedidos)
    pedido_updates = await _update_from_pedidos(db)
    result["pedido_updates"] = pedido_updates

    await db.commit()
    return result


async def _update_from_pedidos(db: AsyncSession) -> int:
    """Actualiza ref_price de insumos usando precios seleccionados de pedidos completados."""
    # Find selected precios from completed pedidos that link to an insumo
    query = (
        select(
            PedidoItem.insumo_id,
            func.avg(PedidoPrecio.unit_price).label("avg_price"),
            func.count(PedidoPrecio.id).label("cnt"),
        )
        .join(PedidoItem, PedidoPrecio.pedido_item_id == PedidoItem.id)
        .join(Pedido, PedidoItem.pedido_id == Pedido.id)
        .where(
            PedidoPrecio.is_selected == True,  # noqa: E712
            PedidoItem.insumo_id.isnot(None),
            Pedido.state == "completed",
        )
        .group_by(PedidoItem.insumo_id)
    )
    rows = (await db.execute(query)).all()

    updated = 0
    for row in rows:
        insumo = await db.get(Insumo, row.insumo_id)
        if not insumo:
            continue
        # Only update if we have no existing ref_price or the pedido data is newer
        if insumo.ref_price is None or row.cnt >= 2:
            insumo.ref_price = round(float(row.avg_price), 2)
            updated += 1

    return updated
