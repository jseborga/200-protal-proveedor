"""Webhook endpoints for external integrations (n8n, MCP, Zapier, etc.)

Auth: X-API-Key header. Set ADMIN_API_KEY in environment variables.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_api_key
from app.models.supplier import Supplier, SupplierBranch, SupplierBranchContact
from app.models.insumo import Insumo
from app.models.price_history import PriceHistory

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────
class SupplierIn(BaseModel):
    name: str
    trade_name: str | None = None
    nit: str | None = None
    email: str | None = None
    phone: str | None = None
    phone2: str | None = None
    whatsapp: str | None = None
    city: str | None = None
    department: str | None = None
    country: str = "BO"
    address: str | None = None
    website: str | None = None
    description: str | None = None
    operating_cities: list[str] | None = None
    categories: list[str] | None = None
    preferred_channel: str = "whatsapp"
    verification_state: str = "verified"
    is_active: bool | None = None
    latitude: float | None = None
    longitude: float | None = None


class SupplierUpdateIn(BaseModel):
    name: str | None = None
    trade_name: str | None = None
    nit: str | None = None
    email: str | None = None
    phone: str | None = None
    phone2: str | None = None
    whatsapp: str | None = None
    city: str | None = None
    department: str | None = None
    country: str | None = None
    address: str | None = None
    website: str | None = None
    description: str | None = None
    operating_cities: list[str] | None = None
    categories: list[str] | None = None
    preferred_channel: str | None = None
    verification_state: str | None = None
    is_active: bool | None = None
    latitude: float | None = None
    longitude: float | None = None


class SupplierRubroIn(BaseModel):
    supplier_id: int
    rubro: str
    description: str | None = None
    category_key: str | None = None
    sort_order: int = 0


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


class PriceHistoryIn(BaseModel):
    insumo_id: int | None = None
    product_name: str | None = None
    supplier_id: int | None = None
    supplier_name: str | None = None
    unit_price: float
    currency: str = "BOB"
    quantity: float | None = None
    uom: str | None = None
    observed_date: date
    source: str = "import"
    source_ref: str | None = None
    notes: str | None = None


class BulkPriceHistoryIn(BaseModel):
    records: list[PriceHistoryIn]


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
    body: SupplierUpdateIn,
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


# ── Supplier Rubros ───────────────────────────────────────────
@router.post("/supplier-rubros")
async def create_supplier_rubro(
    body: SupplierRubroIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Add a rubro (product line) to a supplier."""
    from app.models.supplier import SupplierRubro

    supplier = await db.get(Supplier, body.supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    # Check duplicate
    existing = await db.execute(
        select(SupplierRubro).where(
            SupplierRubro.supplier_id == body.supplier_id,
            SupplierRubro.rubro == body.rubro,
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        return {"ok": True, "action": "skipped", "reason": "already_exists"}

    rubro = SupplierRubro(
        supplier_id=body.supplier_id,
        rubro=body.rubro,
        description=body.description,
        category_key=body.category_key,
        sort_order=body.sort_order,
    )
    db.add(rubro)
    await db.flush()
    return {"ok": True, "action": "created", "data": {
        "id": rubro.id, "rubro": rubro.rubro, "supplier_id": rubro.supplier_id,
    }}


@router.get("/supplier-rubros/{supplier_id}")
async def list_supplier_rubros(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """List rubros for a supplier."""
    from app.models.supplier import SupplierRubro

    result = await db.execute(
        select(SupplierRubro).where(
            SupplierRubro.supplier_id == supplier_id,
            SupplierRubro.is_active == True,
        ).order_by(SupplierRubro.sort_order)
    )
    rubros = result.scalars().all()
    return {"ok": True, "data": [{
        "id": r.id, "rubro": r.rubro, "description": r.description,
        "category_key": r.category_key, "sort_order": r.sort_order,
    } for r in rubros]}


@router.delete("/supplier-rubros/{rubro_id}")
async def delete_supplier_rubro(
    rubro_id: int,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Delete (deactivate) a supplier rubro."""
    from app.models.supplier import SupplierRubro

    rubro = await db.get(SupplierRubro, rubro_id)
    if not rubro:
        raise HTTPException(status_code=404, detail="Rubro not found")
    rubro.is_active = False
    await db.flush()
    return {"ok": True, "action": "deleted", "id": rubro_id}


# ── Supplier Detail (with branches) ───────────────────────────
@router.get("/suppliers/{supplier_id}/detail")
async def get_supplier_detail(
    supplier_id: int,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Full supplier detail incluyendo sucursales y contactos."""
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Supplier).options(
            selectinload(Supplier.branches).selectinload(SupplierBranch.contacts),
        ).where(Supplier.id == supplier_id)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return {
        "ok": True,
        "data": {
            **_sup_dict(s),
            "branches": [
                {**_branch_dict(b), "contacts": [_contact_dict(c) for c in b.contacts if c.is_active]}
                for b in s.branches if b.is_active
            ],
        },
    }


# ── Supplier Branches ─────────────────────────────────────────
class BranchIn(BaseModel):
    supplier_id: int
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


class BranchUpdateIn(BaseModel):
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


@router.get("/branches/{supplier_id}")
async def list_branches(
    supplier_id: int,
    include_contacts: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Lista sucursales activas de un proveedor."""
    if include_contacts:
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(SupplierBranch)
            .options(selectinload(SupplierBranch.contacts))
            .where(SupplierBranch.supplier_id == supplier_id, SupplierBranch.is_active == True)
            .order_by(SupplierBranch.is_main.desc(), SupplierBranch.id)
        )
        branches = result.scalars().all()
        data = [
            {**_branch_dict(b), "contacts": [_contact_dict(c) for c in b.contacts if c.is_active]}
            for b in branches
        ]
    else:
        result = await db.execute(
            select(SupplierBranch)
            .where(SupplierBranch.supplier_id == supplier_id, SupplierBranch.is_active == True)
            .order_by(SupplierBranch.is_main.desc(), SupplierBranch.id)
        )
        data = [_branch_dict(b) for b in result.scalars().all()]
    return {"ok": True, "data": data}


@router.post("/branches")
async def create_branch(
    body: BranchIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Crea una sucursal para un proveedor. Si is_main=True desmarca las otras."""
    supplier = await db.get(Supplier, body.supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    # Dedup por supplier_id + branch_name
    existing = await db.execute(
        select(SupplierBranch).where(
            SupplierBranch.supplier_id == body.supplier_id,
            SupplierBranch.branch_name == body.branch_name,
            SupplierBranch.is_active == True,
        ).limit(1)
    )
    dup = existing.scalar_one_or_none()
    if dup:
        return {"ok": True, "action": "skipped", "reason": "already_exists", "data": _branch_dict(dup)}

    if body.is_main:
        # Desmarcar otras main
        await db.execute(
            text("UPDATE mkt_supplier_branch SET is_main = false WHERE supplier_id = :sid"),
            {"sid": body.supplier_id},
        )

    branch = SupplierBranch(**body.model_dump())
    db.add(branch)
    await db.flush()
    return {"ok": True, "action": "created", "data": _branch_dict(branch)}


@router.put("/branches/{branch_id}")
async def update_branch(
    branch_id: int,
    body: BranchUpdateIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Actualiza una sucursal. Solo los campos enviados."""
    branch = await db.get(SupplierBranch, branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    data = body.model_dump(exclude_unset=True)
    if data.get("is_main") is True:
        await db.execute(
            text("UPDATE mkt_supplier_branch SET is_main = false WHERE supplier_id = :sid AND id != :bid"),
            {"sid": branch.supplier_id, "bid": branch_id},
        )

    for field, value in data.items():
        setattr(branch, field, value)
    await db.flush()
    return {"ok": True, "action": "updated", "data": _branch_dict(branch)}


@router.delete("/branches/{branch_id}")
async def delete_branch(
    branch_id: int,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Desactiva una sucursal."""
    branch = await db.get(SupplierBranch, branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    branch.is_active = False
    await db.flush()
    return {"ok": True, "action": "deleted", "id": branch_id}


# ── Branch Contacts ───────────────────────────────────────────
class BranchContactIn(BaseModel):
    branch_id: int
    full_name: str
    position: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    is_primary: bool = False


class BranchContactUpdateIn(BaseModel):
    full_name: str | None = None
    position: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    email: str | None = None
    is_primary: bool | None = None
    is_active: bool | None = None


@router.post("/branch-contacts")
async def create_branch_contact(
    body: BranchContactIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Agrega un contacto a una sucursal."""
    branch = await db.get(SupplierBranch, body.branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    existing = await db.execute(
        select(SupplierBranchContact).where(
            SupplierBranchContact.branch_id == body.branch_id,
            SupplierBranchContact.full_name == body.full_name,
            SupplierBranchContact.is_active == True,
        ).limit(1)
    )
    dup = existing.scalar_one_or_none()
    if dup:
        return {"ok": True, "action": "skipped", "reason": "already_exists", "data": _contact_dict(dup)}

    contact = SupplierBranchContact(**body.model_dump())
    db.add(contact)
    await db.flush()
    return {"ok": True, "action": "created", "data": _contact_dict(contact)}


@router.put("/branch-contacts/{contact_id}")
async def update_branch_contact(
    contact_id: int,
    body: BranchContactUpdateIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    contact = await db.get(SupplierBranchContact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(contact, field, value)
    await db.flush()
    return {"ok": True, "action": "updated", "data": _contact_dict(contact)}


@router.delete("/branch-contacts/{contact_id}")
async def delete_branch_contact(
    contact_id: int,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    contact = await db.get(SupplierBranchContact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    contact.is_active = False
    await db.flush()
    return {"ok": True, "action": "deleted", "id": contact_id}


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


# ── Price History ─────────────────────────────────────────────
@router.post("/prices/bulk")
async def create_price_history_bulk(
    body: BulkPriceHistoryIn,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Upload price history records in bulk.

    Each record can reference insumo by ID or by product_name (resolved to insumo).
    Supplier can be referenced by ID or supplier_name.
    """
    created, skipped, errors = 0, 0, 0
    error_details = []

    for rec in body.records:
        # Resolve insumo
        insumo_id = rec.insumo_id
        if not insumo_id and rec.product_name:
            insumo = await _find_product_by_name(db, rec.product_name)
            if insumo:
                insumo_id = insumo.id

        if not insumo_id:
            errors += 1
            error_details.append({"product": rec.product_name, "reason": "insumo_not_found"})
            continue

        # Resolve supplier
        supplier_id = rec.supplier_id
        if not supplier_id and rec.supplier_name:
            supplier = await _find_supplier_by_name(db, rec.supplier_name)
            if supplier:
                supplier_id = supplier.id

        # Check for duplicate (same insumo + supplier + date + source_ref)
        if rec.source_ref:
            existing = await db.execute(
                select(PriceHistory).where(
                    PriceHistory.insumo_id == insumo_id,
                    PriceHistory.supplier_id == supplier_id,
                    PriceHistory.observed_date == rec.observed_date,
                    PriceHistory.source_ref == rec.source_ref,
                ).limit(1)
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue

        ph = PriceHistory(
            insumo_id=insumo_id,
            supplier_id=supplier_id,
            unit_price=rec.unit_price,
            currency=rec.currency,
            quantity=rec.quantity,
            uom=rec.uom,
            observed_date=rec.observed_date,
            source=rec.source,
            source_ref=rec.source_ref,
            notes=rec.notes,
        )
        db.add(ph)
        created += 1

    if created:
        await db.flush()

    return {
        "ok": True,
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "error_details": error_details[:20],
    }


@router.get("/prices/history/{insumo_id}")
async def get_price_history(
    insumo_id: int,
    supplier_id: int | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    source: str | None = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Get price history for a specific insumo."""
    query = select(PriceHistory).where(PriceHistory.insumo_id == insumo_id)
    if supplier_id:
        query = query.where(PriceHistory.supplier_id == supplier_id)
    if date_from:
        query = query.where(PriceHistory.observed_date >= date_from)
    if date_to:
        query = query.where(PriceHistory.observed_date <= date_to)
    if source:
        query = query.where(PriceHistory.source == source)

    query = query.order_by(PriceHistory.observed_date.desc()).limit(limit)
    result = await db.execute(query)
    records = result.scalars().all()

    return {
        "ok": True,
        "data": [_ph_dict(r) for r in records],
        "total": len(records),
    }


@router.get("/prices/evolution/{insumo_id}")
async def get_price_evolution(
    insumo_id: int,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Get price evolution stats for an insumo: min, max, avg, median by year."""
    result = await db.execute(
        text("""
            SELECT
                EXTRACT(YEAR FROM observed_date)::int AS year,
                COUNT(*) AS samples,
                ROUND(AVG(unit_price)::numeric, 2) AS avg_price,
                ROUND(MIN(unit_price)::numeric, 2) AS min_price,
                ROUND(MAX(unit_price)::numeric, 2) AS max_price,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY unit_price)::numeric, 2) AS median_price
            FROM mkt_price_history
            WHERE insumo_id = :insumo_id
            GROUP BY EXTRACT(YEAR FROM observed_date)
            ORDER BY year
        """),
        {"insumo_id": insumo_id},
    )
    rows = result.mappings().all()
    return {
        "ok": True,
        "insumo_id": insumo_id,
        "evolution": [dict(r) for r in rows],
    }


# ── Purge ─────────────────────────────────────────────────────
@router.delete("/purge")
async def purge_all_data(
    confirm: str = Query(..., description="Must be 'yes' to confirm"),
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Delete ALL suppliers, products and price history. Requires confirm=yes."""
    if confirm != "yes":
        raise HTTPException(status_code=400, detail="Set confirm=yes to proceed")

    ph = (await db.execute(select(func.count(PriceHistory.id)))).scalar() or 0
    prod = (await db.execute(select(func.count(Insumo.id)))).scalar() or 0
    sup = (await db.execute(select(func.count(Supplier.id)))).scalar() or 0

    await db.execute(text("DELETE FROM mkt_price_history"))
    await db.execute(text("DELETE FROM mkt_product_match"))
    await db.execute(text("DELETE FROM mkt_insumo_regional_price"))
    await db.execute(text("DELETE FROM mkt_insumo"))
    await db.execute(text("DELETE FROM mkt_quotation_line"))
    await db.execute(text("DELETE FROM mkt_quotation"))
    await db.execute(text("DELETE FROM mkt_supplier WHERE user_id IS NULL"))

    return {
        "ok": True,
        "deleted": {"price_records": ph, "products": prod, "suppliers": sup},
    }


# ── Admin SQL cleanup ─────────────────────────────────────────
@router.post("/admin/sql")
async def run_admin_sql(
    body: dict,
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Run a pre-approved admin SQL statement. Requires confirm=yes."""
    if body.get("confirm") != "yes":
        raise HTTPException(status_code=400, detail="Set confirm=yes")

    sql = body.get("sql", "").strip()
    if not sql:
        raise HTTPException(status_code=400, detail="No SQL provided")

    # Safety: only allow DELETE/SELECT
    first_word = sql.split()[0].upper() if sql else ""
    if first_word not in ("DELETE", "SELECT"):
        raise HTTPException(status_code=400, detail="Only DELETE and SELECT allowed")

    result = await db.execute(text(sql))
    rowcount = result.rowcount if hasattr(result, "rowcount") else 0

    return {"ok": True, "sql": sql[:200], "rowcount": rowcount}


# ── Stats ──────────────────────────────────────────────────────
@router.get("/stats")
async def integration_stats(
    db: AsyncSession = Depends(get_db),
    auth: dict = Depends(verify_api_key),
):
    """Quick stats for monitoring."""
    suppliers = (await db.execute(select(func.count(Supplier.id)).where(Supplier.is_active == True))).scalar() or 0
    products = (await db.execute(select(func.count(Insumo.id)).where(Insumo.is_active == True))).scalar() or 0
    price_records = (await db.execute(select(func.count(PriceHistory.id)))).scalar() or 0
    return {"ok": True, "suppliers": suppliers, "products": products, "price_records": price_records}


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
        "nit": s.nit,
        "phone": s.phone, "phone2": s.phone2, "whatsapp": s.whatsapp,
        "email": s.email, "website": s.website,
        "city": s.city, "department": s.department, "address": s.address,
        "latitude": s.latitude, "longitude": s.longitude,
        "description": s.description, "operating_cities": s.operating_cities,
        "categories": s.categories, "verification_state": s.verification_state,
    }


def _branch_dict(b: SupplierBranch) -> dict:
    return {
        "id": b.id, "supplier_id": b.supplier_id,
        "branch_name": b.branch_name,
        "city": b.city, "department": b.department, "address": b.address,
        "phone": b.phone, "whatsapp": b.whatsapp, "email": b.email,
        "latitude": b.latitude, "longitude": b.longitude,
        "is_main": b.is_main, "is_active": b.is_active,
    }


def _contact_dict(c: SupplierBranchContact) -> dict:
    return {
        "id": c.id, "branch_id": c.branch_id,
        "full_name": c.full_name, "position": c.position,
        "phone": c.phone, "whatsapp": c.whatsapp, "email": c.email,
        "is_primary": c.is_primary, "is_active": c.is_active,
    }


def _prod_dict(i: Insumo) -> dict:
    return {
        "id": i.id, "name": i.name, "code": i.code,
        "uom": i.uom, "category": i.category,
        "ref_price": i.ref_price, "ref_currency": i.ref_currency,
    }


async def _find_product_by_name(db, name: str) -> Insumo | None:
    from app.services.matching import normalize_text
    name_norm = normalize_text(name)
    result = await db.execute(
        select(Insumo).where(
            Insumo.name_normalized == name_norm,
            Insumo.is_active == True,
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def _find_supplier_by_name(db, name: str) -> Supplier | None:
    result = await db.execute(
        select(Supplier).where(
            Supplier.name == name,
            Supplier.is_active == True,
        ).limit(1)
    )
    return result.scalar_one_or_none()


def _ph_dict(r: PriceHistory) -> dict:
    return {
        "id": r.id,
        "insumo_id": r.insumo_id,
        "supplier_id": r.supplier_id,
        "unit_price": r.unit_price,
        "currency": r.currency,
        "quantity": r.quantity,
        "uom": r.uom,
        "observed_date": r.observed_date.isoformat(),
        "source": r.source,
        "source_ref": r.source_ref,
    }
