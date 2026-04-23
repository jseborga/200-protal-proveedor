"""Endpoints para pedidos de cotizacion."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.pedido import Pedido, PedidoItem, PedidoPrecio
from app.models.user import User
from app.services.pedido import (
    create_pedido, get_pedido_detail, record_price, complete_pedido,
)

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────
class PedidoItemIn(BaseModel):
    insumo_id: int | None = None
    name: str
    uom: str | None = None
    quantity: float = 1.0
    ref_price: float | None = None
    notes: str | None = None


class PedidoCreate(BaseModel):
    title: str
    description: str | None = None
    region: str | None = None
    currency: str = "BOB"
    deadline: datetime | None = None
    client_whatsapp: str | None = None
    items: list[PedidoItemIn]


class PedidoUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    region: str | None = None
    currency: str | None = None
    deadline: datetime | None = None


class ItemUpdate(BaseModel):
    quantity: float | None = None
    notes: str | None = None


class PrecioIn(BaseModel):
    supplier_id: int | None = None
    supplier_name_text: str | None = None
    unit_price: float
    currency: str = "BOB"
    source: str = "manual"
    notes: str | None = None


class PrecioUpdate(BaseModel):
    unit_price: float | None = None
    supplier_name_text: str | None = None
    notes: str | None = None


# ── Helpers ────────────────────────────────────────────────────
def _pedido_to_dict(p: Pedido) -> dict:
    return {
        "id": p.id,
        "reference": p.reference,
        "title": p.title,
        "description": p.description,
        "state": p.state,
        "created_by": p.created_by,
        "creator_name": p.creator.full_name if p.creator else None,
        "assigned_to": p.assigned_to,
        "region": p.region,
        "currency": p.currency,
        "deadline": p.deadline.isoformat() if p.deadline else None,
        "completed_at": p.completed_at.isoformat() if p.completed_at else None,
        "item_count": p.item_count,
        "quotes_received": p.quotes_received,
        "created_at": p.created_at.isoformat(),
    }


def _item_to_dict(i: PedidoItem) -> dict:
    return {
        "id": i.id,
        "insumo_id": i.insumo_id,
        "sequence": i.sequence,
        "name": i.name,
        "uom": i.uom,
        "quantity": i.quantity,
        "ref_price": i.ref_price,
        "notes": i.notes,
        "precios": [_precio_to_dict(p) for p in (i.precios or [])],
    }


def _precio_to_dict(p: PedidoPrecio) -> dict:
    return {
        "id": p.id,
        "supplier_id": p.supplier_id,
        "supplier_name_text": p.supplier_name_text,
        "unit_price": p.unit_price,
        "currency": p.currency,
        "source": p.source,
        "source_ref": p.source_ref,
        "notes": p.notes,
        "is_selected": p.is_selected,
        "created_at": p.created_at.isoformat(),
    }


async def _get_user_pedido(db: AsyncSession, pedido_id: int, user: User) -> Pedido:
    """Get pedido and verify ownership or company membership."""
    pedido = await get_pedido_detail(db, pedido_id)
    if not pedido:
        raise HTTPException(404, "Pedido no encontrado")
    # Direct ownership
    if pedido.created_by == user.id or pedido.assigned_to == user.id:
        return pedido
    # Company membership — any member can access company pedidos
    if user.company_id and pedido.company_id == user.company_id:
        return pedido
    raise HTTPException(403, "No tienes acceso a este pedido")


# ── CRUD Pedidos ───────────────────────────────────────────────
@router.get("")
async def list_pedidos(
    state: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Listar mis pedidos (incluye pedidos de mi empresa)."""
    if user.company_id:
        query = select(Pedido).where(
            (Pedido.created_by == user.id)
            | (Pedido.assigned_to == user.id)
            | (Pedido.company_id == user.company_id)
        )
    else:
        query = select(Pedido).where(
            (Pedido.created_by == user.id) | (Pedido.assigned_to == user.id)
        )
    if state:
        query = query.where(Pedido.state == state)

    total = (await db.execute(
        select(func.count()).select_from(query.subquery())
    )).scalar() or 0

    query = query.order_by(Pedido.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    pedidos = result.scalars().all()

    return {"ok": True, "data": [_pedido_to_dict(p) for p in pedidos], "total": total}


@router.get("/{pedido_id}")
async def get_pedido(
    pedido_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Detalle de pedido con items y precios."""
    pedido = await _get_user_pedido(db, pedido_id, user)
    data = _pedido_to_dict(pedido)
    data["items"] = [_item_to_dict(i) for i in pedido.items]

    # Link WA de confirmacion regenerado stateless para seguimiento
    from app.services.conversation_hub import build_wa_confirmation_url
    creator = pedido.creator
    data["wa_confirmation_url"] = await build_wa_confirmation_url(pedido, creator)

    return {"ok": True, "data": data}


@router.post("", status_code=201)
async def create(
    body: PedidoCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Crear pedido desde el carrito.

    Además del pedido, abre una ConversationSession y crea el topic en el
    grupo de Telegram de operadores. Devuelve una wa.me URL prellenada que
    el cliente debe abrir para iniciar la conversación WA con el bot.
    """
    if not body.items:
        raise HTTPException(400, "El pedido debe tener al menos un item")

    client_wa = body.client_whatsapp or user.phone

    pedido = await create_pedido(
        db, user,
        title=body.title,
        items=[i.model_dump() for i in body.items],
        region=body.region,
        currency=body.currency,
        description=body.description,
        deadline=body.deadline,
        company_id=user.company_id,
        client_whatsapp=client_wa,
    )

    # Open conversation session + Telegram topic
    from app.services.conversation_hub import open_session, build_wa_confirmation_url
    pedido_full = await get_pedido_detail(db, pedido.id)
    await open_session(db, pedido_full, client_phone=client_wa)
    await db.commit()

    wa_url = await build_wa_confirmation_url(pedido_full, user)

    data = _pedido_to_dict(pedido)
    data["wa_confirmation_url"] = wa_url
    return {"ok": True, "data": data}


@router.put("/{pedido_id}")
async def update_pedido(
    pedido_id: int,
    body: PedidoUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pedido = await _get_user_pedido(db, pedido_id, user)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(pedido, k, v)
    await db.commit()
    await db.refresh(pedido)
    return {"ok": True, "data": _pedido_to_dict(pedido)}


@router.delete("/{pedido_id}")
async def delete_pedido(
    pedido_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pedido = await _get_user_pedido(db, pedido_id, user)
    if pedido.state not in ("draft", "cancelled"):
        raise HTTPException(400, "Solo se pueden eliminar pedidos en borrador o cancelados")
    await db.delete(pedido)
    await db.commit()
    return {"ok": True}


# ── Items ──────────────────────────────────────────────────────
@router.post("/{pedido_id}/items")
async def add_items(
    pedido_id: int,
    items: list[PedidoItemIn],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pedido = await _get_user_pedido(db, pedido_id, user)
    max_seq = max((i.sequence for i in pedido.items), default=-1)

    added = 0
    for item_data in items:
        max_seq += 1
        pi = PedidoItem(
            pedido_id=pedido.id,
            insumo_id=item_data.insumo_id,
            sequence=max_seq,
            name=item_data.name,
            uom=item_data.uom,
            quantity=item_data.quantity,
            ref_price=item_data.ref_price,
            notes=item_data.notes,
        )
        db.add(pi)
        added += 1

    pedido.item_count += added
    await db.commit()
    return {"ok": True, "added": added}


@router.delete("/{pedido_id}/items/{item_id}")
async def remove_item(
    pedido_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_user_pedido(db, pedido_id, user)
    item = await db.get(PedidoItem, item_id)
    if not item or item.pedido_id != pedido_id:
        raise HTTPException(404, "Item no encontrado")
    await db.delete(item)
    pedido = await db.get(Pedido, pedido_id)
    pedido.item_count = max(0, pedido.item_count - 1)
    await db.commit()
    return {"ok": True}


@router.put("/{pedido_id}/items/{item_id}")
async def update_item(
    pedido_id: int,
    item_id: int,
    body: ItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_user_pedido(db, pedido_id, user)
    item = await db.get(PedidoItem, item_id)
    if not item or item.pedido_id != pedido_id:
        raise HTTPException(404, "Item no encontrado")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(item, k, v)
    await db.commit()
    return {"ok": True}


# ── Precios ────────────────────────────────────────────────────
@router.post("/{pedido_id}/items/{item_id}/precio")
async def add_precio(
    pedido_id: int,
    item_id: int,
    body: PrecioIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pedido = await _get_user_pedido(db, pedido_id, user)
    item = await db.get(PedidoItem, item_id)
    if not item or item.pedido_id != pedido_id:
        raise HTTPException(404, "Item no encontrado")

    precio = await record_price(
        db, item_id,
        unit_price=body.unit_price,
        supplier_id=body.supplier_id,
        supplier_name_text=body.supplier_name_text,
        currency=body.currency,
        source=body.source,
        notes=body.notes,
    )

    # Notify pedido creator if someone else added the price
    if user.id != pedido.created_by:
        from app.services.notifications import notify_price_found
        await notify_price_found(db, item, pedido)
        await db.commit()

    return {"ok": True, "data": _precio_to_dict(precio)}


@router.put("/{pedido_id}/items/{item_id}/precio/{precio_id}")
async def update_precio(
    pedido_id: int,
    item_id: int,
    precio_id: int,
    body: PrecioUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_user_pedido(db, pedido_id, user)
    precio = await db.get(PedidoPrecio, precio_id)
    if not precio or precio.pedido_item_id != item_id:
        raise HTTPException(404, "Precio no encontrado")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(precio, k, v)
    await db.commit()
    return {"ok": True}


@router.post("/{pedido_id}/items/{item_id}/precio/{precio_id}/select")
async def select_precio(
    pedido_id: int,
    item_id: int,
    precio_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Marcar un precio como el seleccionado/ganador."""
    await _get_user_pedido(db, pedido_id, user)
    # Deselect all prices for this item
    result = await db.execute(
        select(PedidoPrecio).where(PedidoPrecio.pedido_item_id == item_id)
    )
    for p in result.scalars().all():
        p.is_selected = (p.id == precio_id)
    await db.commit()
    return {"ok": True}


# ── Actions ────────────────────────────────────────────────────
@router.post("/{pedido_id}/complete")
async def mark_complete(
    pedido_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pedido = await _get_user_pedido(db, pedido_id, user)
    if pedido.state == "completed":
        raise HTTPException(400, "El pedido ya esta completado")
    pedido = await complete_pedido(db, pedido)

    from app.services.notifications import notify_pedido_completed
    await notify_pedido_completed(db, pedido)

    # Cerrar la sesión del hub de conversaciones si existe. Capturamos el
    # prev_state para emitir session.state_changed por WS (5.11).
    closed_info: tuple[int, str | None] | None = None
    try:
        from app.models.conversation import ConversationSession as _CSess
        _q = await db.execute(
            select(_CSess)
            .where(_CSess.pedido_id == pedido.id)
            .order_by(_CSess.id.desc())
            .limit(1)
        )
        _sess = _q.scalar_one_or_none()
        if _sess is not None:
            closed_info = (_sess.id, _sess.state)
        from app.services.conversation_hub import close_session_for_pedido
        await close_session_for_pedido(db, pedido.id)
    except Exception as e:
        print(f"[pedido] close_session_for_pedido error: {e}")

    await db.commit()

    if closed_info is not None and closed_info[1] != "closed":
        try:
            from app.services.inbox_ws import publish_session_state_changed as _ws_state_changed
            await _ws_state_changed(
                session_id=closed_info[0],
                prev_state=closed_info[1],
                state="closed",
                pedido_id=pedido.id,
                exclude_user_id=user.id,
            )
        except Exception:
            pass

    return {"ok": True, "data": _pedido_to_dict(pedido)}


@router.post("/{pedido_id}/deliver")
async def deliver_quote(
    pedido_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Entregar la cotización al cliente por WhatsApp.

    Solo el operador asignado (o el creador del pedido) puede ejecutarla.
    """
    pedido = await get_pedido_detail(db, pedido_id)
    if not pedido:
        raise HTTPException(404, "Pedido no encontrado")
    if pedido.assigned_to != user.id and pedido.created_by != user.id:
        raise HTTPException(403, "Solo el operador asignado puede entregar la cotización")

    # Capturamos prev_state de la session para emitir session.state_changed.
    from app.models.conversation import ConversationSession as _CSess
    _q = await db.execute(
        select(_CSess)
        .where(_CSess.pedido_id == pedido.id)
        .order_by(_CSess.id.desc())
        .limit(1)
    )
    _sess = _q.scalar_one_or_none()
    _prev_state = _sess.state if _sess else None

    from app.services.conversation_hub import deliver_quote_to_client
    result = await deliver_quote_to_client(db, pedido, operator=user)
    await db.commit()

    if _sess is not None and result.get("ok") and _prev_state != "quote_sent":
        try:
            await db.refresh(_sess)
            if _sess.state == "quote_sent":
                from app.services.inbox_ws import publish_session_state_changed as _ws_state_changed
                await _ws_state_changed(
                    session_id=_sess.id,
                    prev_state=_prev_state,
                    state="quote_sent",
                    pedido_id=pedido.id,
                    mode=result.get("mode"),
                    exclude_user_id=user.id,
                )
        except Exception:
            pass

    return {"ok": result["ok"], "mode": result["mode"], "url": result["url"]}


@router.post("/{pedido_id}/send")
async def send_to_suppliers(
    pedido_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Enviar pedido como RFQ a proveedores (placeholder — Fase 2 completa la integracion)."""
    pedido = await _get_user_pedido(db, pedido_id, user)
    if pedido.state in ("completed", "cancelled"):
        raise HTTPException(400, "No se puede enviar un pedido completado o cancelado")
    pedido.state = "active"
    await db.commit()
    return {"ok": True, "message": "Pedido activado. Funcionalidad de envio a proveedores disponible proximamente."}


@router.post("/{pedido_id}/upload")
async def upload_document(
    pedido_id: int,
    file: UploadFile = File(...),
    supplier_name: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Subir documento (PDF/Excel/imagen) y extraer precios con AI."""
    pedido = await _get_user_pedido(db, pedido_id, user)

    from app.services.ai_extract import extract_quotation_data

    content = await file.read()
    content_type = file.content_type or ""
    filename = file.filename or "upload"

    # Determine source type from content_type/filename
    if "excel" in content_type or filename.endswith((".xlsx", ".xls")):
        source = "excel"
    elif "pdf" in content_type or filename.endswith(".pdf"):
        source = "pdf"
    elif content_type.startswith("image/") or filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
        source = "photo"
    else:
        source = "pdf"  # fallback

    try:
        result = await extract_quotation_data(content, filename, source, company_id=user.company_id)
    except Exception as e:
        raise HTTPException(400, f"Error extrayendo datos: {str(e)}")

    if not result or not result.get("lines"):
        return {"ok": True, "extracted": 0, "message": "No se pudieron extraer lineas del documento"}

    # Match extracted lines to pedido items and create precios
    items = pedido.items
    created = 0
    matched_lines = []
    for line in result["lines"]:
        extracted_name = (line.get("name") or "").lower().strip()
        extracted_price = line.get("price")
        line_info = {
            "name": line.get("name", ""),
            "price": extracted_price,
            "uom": line.get("uom"),
            "quantity": line.get("quantity"),
        }
        if not extracted_name or not extracted_price:
            line_info["matched_to"] = None
            line_info["score"] = 0
            matched_lines.append(line_info)
            continue

        # Simple name matching against pedido items
        best_item = None
        best_score = 0
        for item in items:
            item_name = item.name.lower()
            words_ext = set(extracted_name.split())
            words_item = set(item_name.split())
            if not words_ext or not words_item:
                continue
            overlap = len(words_ext & words_item) / max(len(words_ext | words_item), 1)
            if overlap > best_score and overlap >= 0.3:
                best_score = overlap
                best_item = item

        if best_item:
            precio = PedidoPrecio(
                pedido_item_id=best_item.id,
                supplier_name_text=supplier_name or None,
                unit_price=float(extracted_price),
                currency=pedido.currency,
                source="upload",
                source_ref=filename,
                notes=f"Extraido de {filename}: {line.get('name', '')}",
            )
            db.add(precio)
            created += 1
            line_info["matched_to"] = {"item_id": best_item.id, "item_name": best_item.name}
            line_info["score"] = round(best_score, 2)
        else:
            line_info["matched_to"] = None
            line_info["score"] = 0

        matched_lines.append(line_info)

    if created:
        await db.commit()

    return {
        "ok": True,
        "extracted": len(result["lines"]),
        "matched": created,
        "lines": matched_lines,
    }
