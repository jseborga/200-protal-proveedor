from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.api.deps import require_manager
from app.models.supplier import Supplier
from app.models.user import User

router = APIRouter()


# ── Schemas ─────────────────────────────────────────────────────
class SupplierCreate(BaseModel):
    name: str
    trade_name: str | None = None
    nit: str | None = None
    email: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    city: str | None = None
    department: str | None = None
    country: str = "BO"
    address: str | None = None
    categories: list[str] | None = None
    preferred_channel: str = "email"


class SupplierUpdate(BaseModel):
    name: str | None = None
    trade_name: str | None = None
    email: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    telegram_chat_id: str | None = None
    city: str | None = None
    department: str | None = None
    address: str | None = None
    categories: list[str] | None = None
    preferred_channel: str | None = None
    verification_state: str | None = None
    is_active: bool | None = None


# ── Endpoints ───────────────────────────────────────────────────
@router.get("")
async def list_suppliers(
    q: str | None = Query(None),
    city: str | None = Query(None),
    category: str | None = Query(None),
    state: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Supplier).where(Supplier.is_active == True)
    if q:
        query = query.where(Supplier.name.ilike(f"%{q}%"))
    if city:
        query = query.where(Supplier.city == city)
    if category:
        query = query.where(Supplier.categories.contains([category]))
    if state:
        query = query.where(Supplier.verification_state == state)

    total_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(total_q)).scalar() or 0

    result = await db.execute(
        query.order_by(Supplier.name).offset(offset).limit(limit)
    )
    suppliers = result.scalars().all()

    return {
        "ok": True,
        "data": [_supplier_to_dict(s) for s in suppliers],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/{supplier_id}")
async def get_supplier(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    return {"ok": True, "data": _supplier_to_dict(supplier)}


@router.post("", status_code=201)
async def create_supplier(
    body: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    supplier = Supplier(**body.model_dump())
    supplier.user_id = user.id if user.role == "supplier" else None
    db.add(supplier)
    await db.flush()
    return {"ok": True, "data": _supplier_to_dict(supplier)}


@router.put("/{supplier_id}")
async def update_supplier(
    supplier_id: int,
    body: SupplierUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(supplier, field, value)
    await db.flush()
    return {"ok": True, "data": _supplier_to_dict(supplier)}


@router.delete("/{supplier_id}")
async def delete_supplier(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    supplier.is_active = False
    await db.flush()
    return {"ok": True}


# ── Helpers ─────────────────────────────────────────────────────
def _supplier_to_dict(s: Supplier) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "trade_name": s.trade_name,
        "nit": s.nit,
        "email": s.email,
        "phone": s.phone,
        "whatsapp": s.whatsapp,
        "city": s.city,
        "department": s.department,
        "country": s.country,
        "categories": s.categories,
        "verification_state": s.verification_state,
        "rating": s.rating,
        "quotation_count": s.quotation_count,
        "preferred_channel": s.preferred_channel,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
