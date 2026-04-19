"""Logica de negocio para pedidos de cotizacion."""

import secrets
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pedido import Pedido, PedidoItem, PedidoPrecio
from app.models.user import User


def _generate_reference() -> str:
    today = date.today().strftime("%Y%m%d")
    suffix = secrets.token_hex(3).upper()
    return f"PED-{today}-{suffix}"


async def create_pedido(
    db: AsyncSession,
    user: User,
    title: str,
    items: list[dict],
    region: str | None = None,
    currency: str = "BOB",
    description: str | None = None,
    deadline: datetime | None = None,
    company_id: int | None = None,
    client_whatsapp: str | None = None,
) -> Pedido:
    """Crea un pedido con sus items desde el carrito del usuario.

    assigned_to se deja en None: un operador/cotizador lo tomará desde el
    grupo de Telegram vía callback (conversation_hub.claim_pedido).
    """
    pedido = Pedido(
        reference=_generate_reference(),
        title=title,
        description=description,
        state="active",
        created_by=user.id,
        assigned_to=None,
        company_id=company_id,
        region=region,
        currency=currency,
        deadline=deadline,
        client_whatsapp=client_whatsapp,
        item_count=len(items),
    )
    db.add(pedido)
    await db.flush()

    for seq, item in enumerate(items):
        pi = PedidoItem(
            pedido_id=pedido.id,
            insumo_id=item.get("insumo_id"),
            sequence=seq,
            name=item["name"],
            uom=item.get("uom"),
            quantity=item.get("quantity", 1.0),
            ref_price=item.get("ref_price"),
            notes=item.get("notes"),
        )
        db.add(pi)

    await db.commit()
    await db.refresh(pedido)
    return pedido


async def get_pedido_detail(db: AsyncSession, pedido_id: int) -> Pedido | None:
    """Carga pedido con items y precios."""
    result = await db.execute(
        select(Pedido)
        .options(
            selectinload(Pedido.items).selectinload(PedidoItem.precios),
        )
        .where(Pedido.id == pedido_id)
    )
    return result.scalars().first()


async def record_price(
    db: AsyncSession,
    pedido_item_id: int,
    unit_price: float,
    supplier_id: int | None = None,
    supplier_name_text: str | None = None,
    currency: str = "BOB",
    source: str = "manual",
    source_ref: str | None = None,
    notes: str | None = None,
) -> PedidoPrecio:
    """Registra un precio encontrado para un item del pedido."""
    precio = PedidoPrecio(
        pedido_item_id=pedido_item_id,
        supplier_id=supplier_id,
        supplier_name_text=supplier_name_text,
        unit_price=unit_price,
        currency=currency,
        source=source,
        source_ref=source_ref,
        notes=notes,
    )
    db.add(precio)

    # Update quotes_received count on the parent pedido
    item = await db.get(PedidoItem, pedido_item_id)
    if item:
        pedido = await db.get(Pedido, item.pedido_id)
        if pedido:
            count = (await db.execute(
                select(func.count(PedidoPrecio.id))
                .join(PedidoItem)
                .where(PedidoItem.pedido_id == pedido.id)
            )).scalar() or 0
            pedido.quotes_received = count + 1

    await db.commit()
    await db.refresh(precio)
    return precio


async def complete_pedido(db: AsyncSession, pedido: Pedido) -> Pedido:
    """Marca un pedido como completado."""
    pedido.state = "completed"
    pedido.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(pedido)
    return pedido
