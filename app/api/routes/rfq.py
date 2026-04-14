import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user
from app.api.deps import require_manager
from app.models.rfq import RFQ, RFQItem
from app.models.supplier import Supplier
from app.models.user import User

router = APIRouter()


# ── Schemas ─────────────────────────────────────────────────────
class RFQItemInput(BaseModel):
    name: str
    uom: str | None = None
    quantity: float = 1.0
    insumo_id: int | None = None
    ref_price: float | None = None
    notes: str | None = None


class RFQCreate(BaseModel):
    title: str
    description: str | None = None
    region: str | None = None
    currency: str = "BOB"
    deadline: datetime | None = None
    supplier_ids: list[int]
    channels: list[str] = ["email"]  # email, whatsapp, telegram
    items: list[RFQItemInput]


# ── Endpoints ───────────────────────────────────────────────────
@router.get("")
async def list_rfqs(
    state: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(RFQ)
    if state:
        query = query.where(RFQ.state == state)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(
        query.order_by(RFQ.created_at.desc()).offset(offset).limit(limit)
    )
    rfqs = result.scalars().all()

    return {"ok": True, "data": [_rfq_to_dict(r) for r in rfqs], "total": total}


@router.get("/{rfq_id}")
async def get_rfq(
    rfq_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(RFQ).where(RFQ.id == rfq_id).options(selectinload(RFQ.items))
    )
    rfq = result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ no encontrada")

    data = _rfq_to_dict(rfq)
    data["items"] = [
        {
            "id": item.id,
            "name": item.name,
            "uom": item.uom,
            "quantity": item.quantity,
            "insumo_id": item.insumo_id,
            "ref_price": item.ref_price,
            "notes": item.notes,
        }
        for item in rfq.items
    ]
    return {"ok": True, "data": data}


@router.post("", status_code=201)
async def create_rfq(
    body: RFQCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    ref = f"RFQ-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    rfq = RFQ(
        reference=ref,
        title=body.title,
        description=body.description,
        region=body.region,
        currency=body.currency,
        deadline=body.deadline,
        created_by=user.id,
        supplier_ids=body.supplier_ids,
        supplier_count=len(body.supplier_ids),
        channels_used=body.channels,
    )
    db.add(rfq)
    await db.flush()

    for i, item_data in enumerate(body.items):
        item = RFQItem(
            rfq_id=rfq.id,
            sequence=i,
            **item_data.model_dump(),
        )
        db.add(item)
    await db.flush()

    return {"ok": True, "data": _rfq_to_dict(rfq)}


@router.post("/{rfq_id}/send")
async def send_rfq(
    rfq_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Send RFQ to suppliers via configured channels."""
    result = await db.execute(
        select(RFQ).where(RFQ.id == rfq_id).options(selectinload(RFQ.items))
    )
    rfq = result.scalar_one_or_none()
    if not rfq:
        raise HTTPException(status_code=404, detail="RFQ no encontrada")
    if rfq.state not in ("draft",):
        raise HTTPException(status_code=400, detail="RFQ ya fue enviada")

    # Load target suppliers
    suppliers_result = await db.execute(
        select(Supplier).where(Supplier.id.in_(rfq.supplier_ids or []))
    )
    suppliers = suppliers_result.scalars().all()

    from app.services.messaging import send_rfq_to_suppliers
    sent = await send_rfq_to_suppliers(rfq, suppliers, rfq.channels_used or ["email"])

    rfq.state = "sent"
    rfq.sent_at = datetime.now(timezone.utc)
    await db.flush()

    return {"ok": True, "sent": sent}


# ── Helpers ─────────────────────────────────────────────────────
def _rfq_to_dict(r: RFQ) -> dict:
    return {
        "id": r.id,
        "reference": r.reference,
        "title": r.title,
        "description": r.description,
        "state": r.state,
        "region": r.region,
        "currency": r.currency,
        "deadline": r.deadline.isoformat() if r.deadline else None,
        "supplier_count": r.supplier_count,
        "response_count": r.response_count,
        "channels_used": r.channels_used,
        "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
