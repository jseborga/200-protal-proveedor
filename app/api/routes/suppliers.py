from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import PUBLIC_LIMIT, limiter
from app.core.security import get_current_user, get_current_user_optional
from app.api.deps import require_manager, require_staff
from sqlalchemy.orm import selectinload

from app.models.supplier import Supplier, SupplierBranch, SupplierBranchContact, SupplierRubro
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
@limiter.limit(PUBLIC_LIMIT)
async def public_suppliers(
    request: Request,
    q: str | None = Query(None),
    city: str | None = Query(None),
    department: str | None = Query(None),
    category: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Public supplier directory — no auth required."""
    query = select(Supplier).where(
        Supplier.is_active == True,
        Supplier.verification_state == "verified",
    )
    if q:
        # Search in name, description, and rubros (product lines)
        pattern = f"%{q}%"
        rubro_match = select(SupplierRubro.supplier_id).where(
            SupplierRubro.is_active == True,
            or_(SupplierRubro.rubro.ilike(pattern), SupplierRubro.description.ilike(pattern)),
        ).correlate(None)
        query = query.where(or_(
            Supplier.name.ilike(pattern),
            Supplier.description.ilike(pattern),
            Supplier.id.in_(rubro_match),
        ))
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

    reveal = user is not None
    return {
        "ok": True,
        "data": [_public_supplier_dict(s, reveal_contacts=reveal) for s in suppliers],
        "total": total,
        "offset": offset,
        "limit": limit,
        "contacts_locked": not reveal,
    }


@router.get("/public/cities")
@limiter.limit(PUBLIC_LIMIT)
async def public_cities(request: Request, db: AsyncSession = Depends(get_db)):
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
@limiter.limit(PUBLIC_LIMIT)
async def public_supplier_categories(request: Request, db: AsyncSession = Depends(get_db)):
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


# ── Public supplier detail ────────────────────────────────────
@router.get("/public/{supplier_id}")
@limiter.limit(PUBLIC_LIMIT)
async def public_supplier_detail(
    request: Request,
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Detalle publico de un proveedor verificado, con sucursales y contactos."""
    result = await db.execute(
        select(Supplier)
        .options(
            selectinload(Supplier.branches).selectinload(SupplierBranch.contacts),
            selectinload(Supplier.rubros),
        )
        .where(
            Supplier.id == supplier_id,
            Supplier.is_active == True,
            Supplier.verification_state == "verified",
        )
    )
    supplier = result.scalars().first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")

    reveal = user is not None

    branches = []
    for b in supplier.branches:
        if not b.is_active:
            continue
        contacts = [
            {
                "full_name": c.full_name,
                "position": c.position,
                "phone": c.phone if reveal else None,
                "whatsapp": c.whatsapp if reveal else None,
                "email": c.email if reveal else None,
                "has_phone": bool(c.phone),
                "has_whatsapp": bool(c.whatsapp),
                "has_email": bool(c.email),
            }
            for c in b.contacts
            if c.is_active
        ]
        branches.append({
            "id": b.id,
            "branch_name": b.branch_name,
            "city": b.city,
            "department": b.department,
            "address": b.address,
            "phone": b.phone if reveal else None,
            "whatsapp": b.whatsapp if reveal else None,
            "email": b.email if reveal else None,
            "has_phone": bool(b.phone),
            "has_whatsapp": bool(b.whatsapp),
            "has_email": bool(b.email),
            "latitude": b.latitude,
            "longitude": b.longitude,
            "is_main": b.is_main,
            "contacts": contacts,
        })

    rubros = [
        {
            "rubro": r.rubro,
            "description": r.description,
            "category_key": r.category_key,
        }
        for r in supplier.rubros
        if r.is_active
    ]

    return {
        "ok": True,
        "data": {
            "id": supplier.id,
            "name": supplier.name,
            "trade_name": supplier.trade_name,
            "description": supplier.description,
            "phone": supplier.phone if reveal else None,
            "phone2": supplier.phone2 if reveal else None,
            "whatsapp": supplier.whatsapp if reveal else None,
            "email": supplier.email if reveal else None,
            "website": supplier.website if reveal else None,
            "has_phone": bool(supplier.phone),
            "has_phone2": bool(supplier.phone2),
            "has_whatsapp": bool(supplier.whatsapp),
            "has_email": bool(supplier.email),
            "has_website": bool(supplier.website),
            "contacts_locked": not reveal,
            "city": supplier.city,
            "department": supplier.department,
            "operating_cities": supplier.operating_cities or [],
            "address": supplier.address,
            "categories": supplier.categories or [],
            "rating": supplier.rating,
            "latitude": supplier.latitude,
            "longitude": supplier.longitude,
            "rubros": rubros,
            "branches": branches,
        },
    }


# ── Nearby endpoint (public) ───────────────────────────────────
@router.get("/public/nearby")
@limiter.limit(PUBLIC_LIMIT)
async def nearby_suppliers(
    request: Request,
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    radius_km: float = Query(50, ge=1, le=200),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """Find nearest suppliers with known coordinates."""
    reveal = user is not None
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
        "contacts_locked": not reveal,
        "data": [
            {
                "id": r["id"], "name": r["name"], "trade_name": r["trade_name"],
                "whatsapp": r["whatsapp"] if reveal else None,
                "phone": r["phone"] if reveal else None,
                "has_whatsapp": bool(r["whatsapp"]),
                "has_phone": bool(r["phone"]),
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
def _public_supplier_dict(s: Supplier, reveal_contacts: bool = False) -> dict:
    """Public-safe fields.

    reveal_contacts=True (usuario autenticado): devuelve telefonos, whatsapp,
    email y website reales.
    reveal_contacts=False (anonimo): los campos de contacto se devuelven como
    None y se anade `has_*` (boolean) + `contacts_locked=True` para que la UI
    muestre "Registrate para ver contacto".
    """
    d = {
        "id": s.id,
        "name": s.name,
        "trade_name": s.trade_name,
        "city": s.city,
        "department": s.department,
        "description": s.description,
        "operating_cities": s.operating_cities,
        "categories": s.categories,
        "rating": s.rating,
        "latitude": s.latitude,
        "longitude": s.longitude,
        "has_phone": bool(s.phone),
        "has_phone2": bool(s.phone2),
        "has_whatsapp": bool(s.whatsapp),
        "has_email": bool(s.email),
        "has_website": bool(s.website),
        "contacts_locked": not reveal_contacts,
    }
    if reveal_contacts:
        d.update({
            "phone": s.phone,
            "phone2": s.phone2,
            "whatsapp": s.whatsapp,
            "email": s.email,
            "website": s.website,
        })
    else:
        d.update({
            "phone": None,
            "phone2": None,
            "whatsapp": None,
            "email": None,
            "website": None,
        })
    return d


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


# ── Contact schemas ───────────────────────────────────────────
class ContactCreate(BaseModel):
    full_name: str
    position: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    is_primary: bool = False


class ContactUpdate(BaseModel):
    full_name: str | None = None
    position: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    is_primary: bool | None = None
    is_active: bool | None = None


def _contact_to_dict(c: SupplierBranchContact) -> dict:
    return {
        "id": c.id,
        "branch_id": c.branch_id,
        "full_name": c.full_name,
        "position": c.position,
        "phone": c.phone,
        "whatsapp": c.whatsapp,
        "email": c.email,
        "is_primary": c.is_primary,
        "is_active": c.is_active,
    }


async def _get_branch_or_404(
    db: AsyncSession, supplier_id: int, branch_id: int
) -> SupplierBranch:
    branch = await db.get(SupplierBranch, branch_id)
    if not branch or branch.supplier_id != supplier_id:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    return branch


# ── Contact endpoints ─────────────────────────────────────────
@router.get("/{supplier_id}/branches/{branch_id}/contacts")
async def list_contacts(
    supplier_id: int,
    branch_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_branch_or_404(db, supplier_id, branch_id)
    result = await db.execute(
        select(SupplierBranchContact)
        .where(SupplierBranchContact.branch_id == branch_id)
        .order_by(
            SupplierBranchContact.is_primary.desc(),
            SupplierBranchContact.full_name,
        )
    )
    contacts = result.scalars().all()
    return {"ok": True, "data": [_contact_to_dict(c) for c in contacts]}


@router.post("/{supplier_id}/branches/{branch_id}/contacts", status_code=201)
async def create_contact(
    supplier_id: int,
    branch_id: int,
    body: ContactCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    await _get_branch_or_404(db, supplier_id, branch_id)
    if body.is_primary:
        existing = (await db.execute(
            select(SupplierBranchContact).where(
                SupplierBranchContact.branch_id == branch_id,
                SupplierBranchContact.is_primary == True,
            )
        )).scalars().all()
        for c in existing:
            c.is_primary = False
    contact = SupplierBranchContact(branch_id=branch_id, **body.model_dump())
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return {"ok": True, "data": _contact_to_dict(contact)}


@router.put("/{supplier_id}/branches/{branch_id}/contacts/{contact_id}")
async def update_contact(
    supplier_id: int,
    branch_id: int,
    contact_id: int,
    body: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    await _get_branch_or_404(db, supplier_id, branch_id)
    contact = await db.get(SupplierBranchContact, contact_id)
    if not contact or contact.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    data = body.model_dump(exclude_unset=True)
    if data.get("is_primary"):
        existing = (await db.execute(
            select(SupplierBranchContact).where(
                SupplierBranchContact.branch_id == branch_id,
                SupplierBranchContact.is_primary == True,
                SupplierBranchContact.id != contact_id,
            )
        )).scalars().all()
        for c in existing:
            c.is_primary = False
    for k, v in data.items():
        setattr(contact, k, v)
    await db.commit()
    await db.refresh(contact)
    return {"ok": True, "data": _contact_to_dict(contact)}


@router.delete("/{supplier_id}/branches/{branch_id}/contacts/{contact_id}")
async def delete_contact(
    supplier_id: int,
    branch_id: int,
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    await _get_branch_or_404(db, supplier_id, branch_id)
    contact = await db.get(SupplierBranchContact, contact_id)
    if not contact or contact.branch_id != branch_id:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    await db.delete(contact)
    await db.commit()
    return {"ok": True}


# ── Supplier suggestions ──────────────────────────────────────
from app.models.supplier_suggestion import SupplierSuggestion
from app.api.deps import require_admin


class SuggestionCreate(BaseModel):
    name: str
    trade_name: str | None = None
    nit: str | None = None
    email: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    city: str | None = None
    department: str | None = None
    address: str | None = None
    categories: list[str] | None = None
    notes: str | None = None


def _suggestion_to_dict(s: SupplierSuggestion) -> dict:
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
        "address": s.address,
        "categories": s.categories or [],
        "notes": s.notes,
        "state": s.state,
        "suggested_by": s.suggested_by,
        "suggester_name": s.suggester.full_name if s.suggester else None,
        "company_id": s.company_id,
        "reviewed_by": s.reviewed_by,
        "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None,
        "review_notes": s.review_notes,
        "created_supplier_id": s.created_supplier_id,
        "created_at": s.created_at.isoformat(),
    }


@router.post("/suggest", status_code=201)
async def suggest_supplier(
    body: SuggestionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Sugerir un proveedor nuevo (cualquier usuario logueado)."""
    suggestion = SupplierSuggestion(
        suggested_by=user.id,
        company_id=getattr(user, 'company_id', None),
        name=body.name,
        trade_name=body.trade_name,
        nit=body.nit,
        email=body.email,
        phone=body.phone,
        whatsapp=body.whatsapp,
        city=body.city,
        department=body.department,
        address=body.address,
        categories=body.categories,
        notes=body.notes,
        state="pending",
    )
    db.add(suggestion)
    await db.commit()
    await db.refresh(suggestion)
    return {"ok": True, "data": _suggestion_to_dict(suggestion)}


@router.get("/suggestions")
async def my_suggestions(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mis sugerencias de proveedores."""
    query = select(SupplierSuggestion).where(SupplierSuggestion.suggested_by == user.id)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(
        query.order_by(SupplierSuggestion.created_at.desc()).offset(offset).limit(limit)
    )
    return {
        "ok": True,
        "data": [_suggestion_to_dict(s) for s in result.scalars().all()],
        "total": total,
    }
