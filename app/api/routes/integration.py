"""Webhook endpoints for external integrations (n8n, MCP, Zapier, etc.)

Auth: X-API-Key header. Set ADMIN_API_KEY in environment variables.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_api_key
from app.models.supplier import Supplier
from app.models.insumo import Insumo

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────
class SupplierIn(BaseModel):
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
    preferred_channel: str = "whatsapp"
    verification_state: str = "verified"


class ProductIn(BaseModel):
    name: str
    code: str | None = None
    uom: str = "pza"
    category: str | None = None
    subcategory: str | None = None
    description: str | None = None
    ref_price: float | None = None
    ref_currency: str = "BOB"


class BulkSuppliersIn(BaseModel):
    suppliers: list[SupplierIn]


class BulkProductsIn(BaseModel):
    products: list[ProductIn]


# ── Suppliers ──────────────────────────────────────────────────
@router.post("/suppliers")
async def create_supplier(
    body: SupplierIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Create a single supplier. Skips if name+city already exists."""
    existing = await _find_supplier(db, body.name, body.city)
    if existing:
        return {"ok": True, "action": "skipped", "reason": "already_exists", "data": _sup_dict(existing)}

    supplier = Supplier(**body.model_dump())
    db.add(supplier)
    await db.flush()
    return {"ok": True, "action": "created", "data": _sup_dict(supplier)}


@router.post("/suppliers/bulk")
async def create_suppliers_bulk(
    body: BulkSuppliersIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Create multiple suppliers. Skips duplicates by name+city."""
    created, skipped = 0, 0
    results = []

    for item in body.suppliers:
        existing = await _find_supplier(db, item.name, item.city)
        if existing:
            skipped += 1
            results.append({"name": item.name, "action": "skipped"})
            continue

        supplier = Supplier(**item.model_dump())
        db.add(supplier)
        await db.flush()
        created += 1
        results.append({"name": item.name, "action": "created", "id": supplier.id})

    return {"ok": True, "created": created, "skipped": skipped, "results": results}


@router.get("/suppliers")
async def list_suppliers(
    q: str | None = Query(None),
    city: str | None = Query(None),
    department: str | None = Query(None),
    category: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """List all suppliers (including unverified)."""
    query = select(Supplier).where(Supplier.is_active == True)
    if q:
        query = query.where(Supplier.name.ilike(f"%{q}%"))
    if city:
        query = query.where(Supplier.city.ilike(f"%{city}%"))
    if department:
        query = query.where(Supplier.department == department)
    if category:
        query = query.where(Supplier.categories.contains([category]))

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(query.order_by(Supplier.id.desc()).offset(offset).limit(limit))
    suppliers = result.scalars().all()

    return {"ok": True, "data": [_sup_dict(s) for s in suppliers], "total": total}


@router.put("/suppliers/{supplier_id}")
async def update_supplier(
    supplier_id: int,
    body: SupplierIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    supplier = await db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(supplier, field, value)
    await db.flush()
    return {"ok": True, "action": "updated", "data": _sup_dict(supplier)}


# ── Products ───────────────────────────────────────────────────
@router.post("/products")
async def create_product(
    body: ProductIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Create a single product. Skips if name+uom already exists."""
    existing = await _find_product(db, body.name, body.uom)
    if existing:
        return {"ok": True, "action": "skipped", "reason": "already_exists", "data": _prod_dict(existing)}

    from app.services.matching import normalize_text, normalize_uom
    insumo = Insumo(
        name=body.name,
        name_normalized=normalize_text(body.name),
        code=body.code,
        uom=body.uom,
        uom_normalized=normalize_uom(body.uom),
        category=body.category,
        subcategory=body.subcategory,
        description=body.description,
        ref_price=body.ref_price,
        ref_currency=body.ref_currency,
    )
    db.add(insumo)
    await db.flush()
    return {"ok": True, "action": "created", "data": _prod_dict(insumo)}


@router.post("/products/bulk")
async def create_products_bulk(
    body: BulkProductsIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Create multiple products. Skips duplicates by name+uom."""
    from app.services.matching import normalize_text, normalize_uom

    created, skipped = 0, 0
    results = []

    for item in body.products:
        existing = await _find_product(db, item.name, item.uom)
        if existing:
            skipped += 1
            results.append({"name": item.name, "action": "skipped"})
            continue

        insumo = Insumo(
            name=item.name,
            name_normalized=normalize_text(item.name),
            code=item.code,
            uom=item.uom,
            uom_normalized=normalize_uom(item.uom),
            category=item.category,
            subcategory=item.subcategory,
            description=item.description,
            ref_price=item.ref_price,
            ref_currency=item.ref_currency,
        )
        db.add(insumo)
        await db.flush()
        created += 1
        results.append({"name": item.name, "action": "created", "id": insumo.id})

    return {"ok": True, "created": created, "skipped": skipped, "results": results}


@router.get("/products")
async def list_products(
    q: str | None = Query(None),
    category: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """List all products."""
    query = select(Insumo).where(Insumo.is_active == True)
    if q:
        query = query.where(Insumo.name.ilike(f"%{q}%"))
    if category:
        query = query.where(Insumo.category == category)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(query.order_by(Insumo.name).offset(offset).limit(limit))
    insumos = result.scalars().all()

    return {"ok": True, "data": [_prod_dict(i) for i in insumos], "total": total}


@router.put("/products/{product_id}")
async def update_product(
    product_id: int,
    body: ProductIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    from app.services.matching import normalize_text, normalize_uom

    insumo = await db.get(Insumo, product_id)
    if not insumo:
        raise HTTPException(status_code=404, detail="Product not found")

    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        data["name_normalized"] = normalize_text(data["name"])
    if "uom" in data:
        data["uom_normalized"] = normalize_uom(data["uom"])

    for field, value in data.items():
        if hasattr(insumo, field):
            setattr(insumo, field, value)
    await db.flush()
    return {"ok": True, "action": "updated", "data": _prod_dict(insumo)}


# ── Stats ──────────────────────────────────────────────────────
@router.get("/stats")
async def integration_stats(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Quick stats for monitoring."""
    suppliers = (await db.execute(select(func.count(Supplier.id)).where(Supplier.is_active == True))).scalar() or 0
    products = (await db.execute(select(func.count(Insumo.id)).where(Insumo.is_active == True))).scalar() or 0
    return {"ok": True, "suppliers": suppliers, "products": products}


# ── Helpers ────────────────────────────────────────────────────
async def _find_supplier(db, name: str, city: str | None) -> Supplier | None:
    q = select(Supplier).where(Supplier.name == name, Supplier.is_active == True)
    if city:
        q = q.where(Supplier.city == city)
    result = await db.execute(q)
    return result.scalar_one_or_none()


async def _find_product(db, name: str, uom: str) -> Insumo | None:
    result = await db.execute(
        select(Insumo).where(Insumo.name == name, Insumo.uom == uom, Insumo.is_active == True)
    )
    return result.scalar_one_or_none()


def _sup_dict(s: Supplier) -> dict:
    return {
        "id": s.id, "name": s.name, "trade_name": s.trade_name,
        "phone": s.phone, "whatsapp": s.whatsapp,
        "city": s.city, "department": s.department,
        "categories": s.categories, "verification_state": s.verification_state,
    }


def _prod_dict(i: Insumo) -> dict:
    return {
        "id": i.id, "name": i.name, "code": i.code,
        "uom": i.uom, "category": i.category,
        "ref_price": i.ref_price, "ref_currency": i.ref_currency,
    }
