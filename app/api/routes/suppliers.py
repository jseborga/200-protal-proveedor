from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.api.deps import require_manager, require_staff
from app.models.supplier import Supplier, SupplierBranch
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
    latitude: float | None = None
    longitude: float | None = None


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
    latitude: float | None = None
    longitude: float | None = None


# ── Public endpoints ────────────────────────────────────────────
@router.get("/public")
async def public_suppliers(
    q: str | None = Query(None),
    city: str | None = Query(None),
    department: str | None = Query(None),
    category: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Public supplier directory — no auth required."""
    query = select(Supplier).where(
        Supplier.is_active == True,
        Supplier.verification_state == "verified",
    )
    if q:
        query = query.where(Supplier.name.ilike(f"%{q}%"))
    if city:
        query = query.where(Supplier.city == city)
    if department:
        query = query.where(Supplier.department == department)
    if category:
        query = query.where(Supplier.categories.contains([category]))

    total_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(total_q)).scalar() or 0

    result = await db.execute(
        query.order_by(Supplier.name).offset(offset).limit(limit)
    )
    suppliers = result.scalars().all()

    return {
        "ok": True,
        "data": [_public_supplier_dict(s) for s in suppliers],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/public/cities")
async def public_cities(db: AsyncSession = Depends(get_db)):
    """List cities with verified suppliers."""
    result = await db.execute(
        select(Supplier.city, Supplier.department, func.count(Supplier.id))
        .where(
            Supplier.is_active == True,
            Supplier.verification_state == "verified",
            Supplier.city.isnot(None),
        )
        .group_by(Supplier.city, Supplier.department)
        .order_by(Supplier.department, Supplier.city)
    )
    return {
        "ok": True,
        "data": [
            {"city": r[0], "department": r[1], "count": r[2]}
            for r in result.all()
        ],
    }


@router.get("/public/categories")
async def public_supplier_categories(db: AsyncSession = Depends(get_db)):
    """List distinct supplier categories with counts."""
    result = await db.execute(
        select(func.unnest(Supplier.categories).label("cat"))
        .where(Supplier.is_active == True, Supplier.verification_state == "verified")
    )
    from collections import Counter
    cats = Counter(r[0] for r in result.all())
    return {
        "ok": True,
        "data": [{"name": k, "count": v} for k, v in sorted(cats.items())],
    }


# ── Nearby endpoint (public) ───────────────────────────────────
@router.get("/public/nearby")
async def nearby_suppliers(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    radius_km: float = Query(50, ge=1, le=500),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Find nearest suppliers with known coordinates."""
    result = await db.execute(text("""
        SELECT *, (
            6371 * acos(
                LEAST(1.0, cos(radians(:lat)) * cos(radians(latitude)) *
                cos(radians(longitude) - radians(:lon)) +
                sin(radians(:lat)) * sin(radians(latitude)))
            )
        ) AS distance_km
        FROM mkt_supplier
        WHERE is_active = true AND verification_state = 'verified'
          AND latitude IS NOT NULL AND longitude IS NOT NULL
        ORDER BY distance_km
        LIMIT :lim
    """), {"lat": lat, "lon": lon, "lim": limit})
    rows = result.mappings().all()
    return {
        "ok": True,
        "data": [
            {
                "id": r["id"], "name": r["name"], "trade_name": r["trade_name"],
                "whatsapp": r["whatsapp"], "phone": r["phone"],
                "city": r["city"], "department": r["department"],
                "latitude": r["latitude"], "longitude": r["longitude"],
                "distance_km": round(r["distance_km"], 1),
                "categories": r["categories"],
            }
            for r in rows if r["distance_km"] <= radius_km
        ],
    }


# ── Authenticated endpoints ────────────────────────────────────
@router.get("")
async def list_suppliers(
    q: str | None = Query(None),
    city: str | None = Query(None),
    category: str | None = Query(None),
    state: str | None = Query(None),
    contact: str | None = Query(None, description="valid_wa, invalid_wa, no_wa"),
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
    # WhatsApp contact filter
    if contact == "no_wa":
        query = query.where(
            (Supplier.whatsapp == None) | (Supplier.whatsapp == "")  # noqa: E711
        )
    elif contact == "invalid_wa":
        # Has a number but not a valid Bolivia mobile format
        query = query.where(
            Supplier.whatsapp != None,  # noqa: E711
            Supplier.whatsapp != "",
            ~Supplier.whatsapp.op("~")(r"^591[67]\d{7}$"),
        )
    elif contact == "valid_wa":
        query = query.where(
            Supplier.whatsapp.op("~")(r"^591[67]\d{7}$"),
        )

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
    user: User = Depends(require_staff),
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


# ── Supplier Products (from price history) ─────────────────────
@router.get("/{supplier_id}/products")
async def get_supplier_products(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get all products a supplier sells, with price stats from order history."""
    result = await db.execute(
        text("""
            SELECT
                ph.insumo_id,
                i.name AS product_name,
                i.uom,
                i.category,
                i.ref_price,
                COUNT(*) AS order_count,
                SUM(ph.quantity) AS total_qty,
                ROUND(AVG(ph.unit_price)::numeric, 2) AS avg_price,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ph.unit_price)::numeric, 2) AS median_price,
                ROUND(MIN(ph.unit_price)::numeric, 2) AS min_price,
                ROUND(MAX(ph.unit_price)::numeric, 2) AS max_price,
                MIN(ph.observed_date) AS first_order,
                MAX(ph.observed_date) AS last_order
            FROM mkt_price_history ph
            JOIN mkt_insumo i ON i.id = ph.insumo_id
            WHERE ph.supplier_id = :supplier_id
            GROUP BY ph.insumo_id, i.name, i.uom, i.category, i.ref_price
            ORDER BY order_count DESC
        """),
        {"supplier_id": supplier_id},
    )
    rows = result.mappings().all()
    return {
        "ok": True,
        "data": [
            {
                **dict(r),
                "total_qty": float(r["total_qty"]) if r["total_qty"] else 0,
                "first_order": r["first_order"].isoformat() if r["first_order"] else None,
                "last_order": r["last_order"].isoformat() if r["last_order"] else None,
            }
            for r in rows
        ],
    }


# ── Helpers ─────────────────────────────────────────────────────
def _public_supplier_dict(s: Supplier) -> dict:
    """Public-safe fields only — no email, NIT, or internal data."""
    return {
        "id": s.id,
        "name": s.name,
        "trade_name": s.trade_name,
        "phone": s.phone,
        "whatsapp": s.whatsapp,
        "city": s.city,
        "department": s.department,
        "categories": s.categories,
        "rating": s.rating,
        "latitude": s.latitude,
        "longitude": s.longitude,
    }


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
        "address": s.address,
        "categories": s.categories,
        "verification_state": s.verification_state,
        "rating": s.rating,
        "quotation_count": s.quotation_count,
        "preferred_channel": s.preferred_channel,
        "latitude": s.latitude,
        "longitude": s.longitude,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _branch_to_dict(b: SupplierBranch) -> dict:
    return {
        "id": b.id,
        "supplier_id": b.supplier_id,
        "branch_name": b.branch_name,
        "city": b.city,
        "department": b.department,
        "address": b.address,
        "phone": b.phone,
        "whatsapp": b.whatsapp,
        "email": b.email,
        "latitude": b.latitude,
        "longitude": b.longitude,
        "is_main": b.is_main,
        "is_active": b.is_active,
    }


# ── Branch schemas ─────────────────────────────────────────────
class BranchCreate(BaseModel):
    branch_name: str
    city: str | None = None
    department: str | None = None
    address: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    is_main: bool = False


class BranchUpdate(BaseModel):
    branch_name: str | None = None
    city: str | None = None
    department: str | None = None
    address: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    is_main: bool | None = None
    is_active: bool | None = None


# ── Branch endpoints ───────────────────────────────────────────
@router.get("/{supplier_id}/branches")
async def list_branches(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    result = await db.execute(
        select(SupplierBranch)
        .where(SupplierBranch.supplier_id == supplier_id)
        .order_by(SupplierBranch.is_main.desc(), SupplierBranch.branch_name)
    )
    branches = result.scalars().all()
    return {"ok": True, "data": [_branch_to_dict(b) for b in branches]}


@router.post("/{supplier_id}/branches", status_code=201)
async def create_branch(
    supplier_id: int,
    body: BranchCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    branch = SupplierBranch(supplier_id=supplier_id, **body.model_dump())
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    return {"ok": True, "data": _branch_to_dict(branch)}


@router.put("/{supplier_id}/branches/{branch_id}")
async def update_branch(
    supplier_id: int,
    branch_id: int,
    body: BranchUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    branch = await db.get(SupplierBranch, branch_id)
    if not branch or branch.supplier_id != supplier_id:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(branch, k, v)
    await db.commit()
    await db.refresh(branch)
    return {"ok": True, "data": _branch_to_dict(branch)}


@router.delete("/{supplier_id}/branches/{branch_id}")
async def delete_branch(
    supplier_id: int,
    branch_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    branch = await db.get(SupplierBranch, branch_id)
    if not branch or branch.supplier_id != supplier_id:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    await db.delete(branch)
    await db.commit()
    return {"ok": True}
