"""Servicio de notificaciones in-app."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


async def notify_user(
    db: AsyncSession,
    user_id: int,
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    data: dict | None = None,
) -> Notification:
    """Crea una notificacion para un usuario."""
    notif = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        link=link,
        data=data,
    )
    db.add(notif)
    await db.flush()
    return notif


async def notify_pedido_completed(db: AsyncSession, pedido) -> None:
    """Notifica al creador que su pedido fue completado."""
    await notify_user(
        db, pedido.created_by,
        type="pedido_completed",
        title=f"Pedido {pedido.reference} completado",
        body=f'Tu pedido "{pedido.title}" ha sido marcado como completado.',
        link=f"pedido/{pedido.id}",
        data={"pedido_id": pedido.id},
    )


async def notify_pedido_assigned(db: AsyncSession, pedido, assignee_id: int) -> None:
    """Notifica al cotizador que se le asigno un pedido."""
    await notify_user(
        db, assignee_id,
        type="pedido_assigned",
        title=f"Pedido {pedido.reference} asignado",
        body=f'Se te asigno el pedido "{pedido.title}" para cotizar.',
        link=f"pedido/{pedido.id}",
        data={"pedido_id": pedido.id},
    )


async def notify_price_found(db: AsyncSession, pedido_item, pedido) -> None:
    """Notifica al creador del pedido que se encontro un precio para un item."""
    await notify_user(
        db, pedido.created_by,
        type="price_found",
        title=f"Precio encontrado: {pedido_item.name}",
        body=f'Se registro un nuevo precio para "{pedido_item.name}" en tu pedido {pedido.reference}.',
        link=f"pedido/{pedido.id}",
        data={"pedido_id": pedido.id, "item_id": pedido_item.id},
    )


async def notify_member_added(db: AsyncSession, user_id: int, company_name: str) -> None:
    """Notifica al usuario que fue agregado a una empresa."""
    await notify_user(
        db, user_id,
        type="member_added",
        title=f"Agregado a {company_name}",
        body=f"Ahora eres miembro del equipo de {company_name}.",
        link="company",
    )


async def notify_suggestion_approved(
    db: AsyncSession, user_id: int, supplier_name: str,
) -> None:
    """Notifica al usuario que su sugerencia de proveedor fue aprobada."""
    await notify_user(
        db, user_id,
        type="suggestion_approved",
        title=f"Proveedor aprobado: {supplier_name}",
        body=f'Tu sugerencia del proveedor "{supplier_name}" fue aprobada y agregada al directorio.',
        link="suppliers",
    )


async def notify_subscription_updated(
    db: AsyncSession, user_id: int, plan_label: str,
) -> None:
    """Notifica al admin de la empresa que su suscripcion fue actualizada."""
    await notify_user(
        db, user_id,
        type="subscription_updated",
        title="Suscripcion actualizada",
        body=f"Tu suscripcion fue actualizada al plan {plan_label}.",
        link="company",
    )
