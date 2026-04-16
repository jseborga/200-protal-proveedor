from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes as sa_attrs

from app.core.database import get_db
from app.core.security import hash_password, verify_api_key, pwd_context
from app.api.deps import require_admin, require_manager, require_staff, STAFF_ROLES
from app.models.insumo import Insumo, InsumoRegionalPrice
from app.models.quotation import Quotation
from app.models.supplier import Supplier, SupplierBranch
from app.models.match import ProductMatch
from app.models.price_history import PriceHistory
from app.models.rfq import RFQ
from app.models.user import User
from app.models.api_key import ApiKey
from app.models.catalog import Category, UnitOfMeasure
from app.models.ai_agent import AIAgent

router = APIRouter()

VALID_ROLES = ("admin", "manager", "field_agent", "user", "supplier")


# ── Stats ──────────────────────────────────────────────────────
@router.get("/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    """Dashboard stats — accessible to all staff."""
    users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    suppliers = (await db.execute(select(func.count(Supplier.id)))).scalar() or 0
    insumos = (await db.execute(select(func.count(Insumo.id)).where(Insumo.is_active == True))).scalar() or 0
    quotations = (await db.execute(select(func.count(Quotation.id)))).scalar() or 0
    regions = (await db.execute(
        select(func.count(func.distinct(InsumoRegionalPrice.region)))
    )).scalar() or 0

    return {
        "ok": True,
        "data": {
            "users": users,
            "suppliers": suppliers,
            "insumos": insumos,
            "quotations": quotations,
            "regions": regions,
        },
    }


# ── User management ───────────────────────────────────────────
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = "field_agent"
    phone: str | None = None
    company_name: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    phone: str | None = None
    company_name: str | None = None
    is_active: bool | None = None


@router.get("/users")
async def list_users(
    q: str | None = Query(None),
    role: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    query = select(User)
    if q:
        query = query.where(
            User.full_name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%")
        )
    if role:
        query = query.where(User.role == role)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(query.order_by(User.created_at.desc()).offset(offset).limit(limit))
    users = result.scalars().all()

    return {
        "ok": True,
        "data": [_user_to_dict(u) for u in users],
        "total": total,
    }


@router.post("/users", status_code=201)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Rol invalido. Opciones: {', '.join(VALID_ROLES)}")

    # Only admins can create admins/managers
    if body.role in ("admin", "manager") and current_user.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Solo admins pueden crear managers/admins")

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email ya registrado")

    new_user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        phone=body.phone,
        company_name=body.company_name,
    )
    db.add(new_user)
    await db.flush()

    return {"ok": True, "data": _user_to_dict(new_user)}


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    update_data = body.model_dump(exclude_unset=True)

    # Role change validation
    if "role" in update_data:
        if update_data["role"] not in VALID_ROLES:
            raise HTTPException(status_code=400, detail="Rol invalido")
        if update_data["role"] in ("admin", "manager") and current_user.role not in ("admin", "superadmin"):
            raise HTTPException(status_code=403, detail="Solo admins pueden asignar rol admin/manager")
        if target.role in ("admin", "superadmin") and current_user.role != "superadmin":
            raise HTTPException(status_code=403, detail="No puede cambiar rol de un admin")

    for field, value in update_data.items():
        setattr(target, field, value)
    await db.flush()

    return {"ok": True, "data": _user_to_dict(target)}


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Reset a user's password to a temporary one."""
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    import secrets
    temp_password = secrets.token_urlsafe(8)
    target.hashed_password = hash_password(temp_password)
    await db.flush()

    return {"ok": True, "temp_password": temp_password}


# ── External API ───────────────────────────────────────────────
@router.get("/api/prices")
async def api_prices(
    category: str | None = Query(None),
    region: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    api_auth: dict = Depends(verify_api_key),
):
    """External API endpoint for ERP integrations (uses API key auth)."""
    query = select(Insumo).where(Insumo.is_active == True)
    if category:
        query = query.where(Insumo.category == category)

    result = await db.execute(query.order_by(Insumo.name).offset(offset).limit(limit))
    insumos = result.scalars().all()

    data = []
    for ins in insumos:
        item = {
            "id": ins.id,
            "code": ins.code,
            "name": ins.name,
            "uom": ins.uom,
            "category": ins.category,
            "ref_price": ins.ref_price,
            "currency": ins.ref_currency,
        }
        if region:
            rp = await db.execute(
                select(InsumoRegionalPrice).where(
                    InsumoRegionalPrice.insumo_id == ins.id,
                    InsumoRegionalPrice.region == region,
                )
            )
            regional = rp.scalar_one_or_none()
            if regional:
                item["regional_price"] = regional.price
                item["confidence"] = regional.confidence
        data.append(item)

    return {"ok": True, "data": data, "total": len(data)}


# ── API Key management ─────────────────────────────────────────
class ApiKeyCreate(BaseModel):
    name: str
    description: str | None = None
    scopes: str = "read,write"
    expires_in_days: int | None = None  # None = no expiration


class ApiKeyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    scopes: str | None = None
    is_active: bool | None = None
    expires_in_days: int | None = None  # reset expiration


@router.get("/api-keys")
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    result = await db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
    keys = result.scalars().all()
    return {
        "ok": True,
        "data": [_apikey_to_dict(k) for k in keys],
    }


@router.post("/api-keys", status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    import secrets
    from datetime import datetime, timezone, timedelta

    # Generate a secure random key
    raw_key = f"mkt_{secrets.token_urlsafe(32)}"

    expires_at = None
    if body.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)

    api_key = ApiKey(
        name=body.name,
        key_hash=pwd_context.hash(raw_key),
        key_prefix=raw_key[:8],
        description=body.description,
        scopes=body.scopes,
        expires_at=expires_at,
        created_by_id=user.id,
    )
    db.add(api_key)
    await db.flush()

    # Return the raw key ONLY on creation — it can't be retrieved later
    data = _apikey_to_dict(api_key)
    data["raw_key"] = raw_key

    return {"ok": True, "data": data}


@router.put("/api-keys/{key_id}")
async def update_api_key(
    key_id: int,
    body: ApiKeyUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    from datetime import datetime, timezone, timedelta

    api_key = await db.get(ApiKey, key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key no encontrada")

    update_data = body.model_dump(exclude_unset=True)

    if "expires_in_days" in update_data:
        days = update_data.pop("expires_in_days")
        if days:
            api_key.expires_at = datetime.now(timezone.utc) + timedelta(days=days)
        else:
            api_key.expires_at = None

    for field, value in update_data.items():
        setattr(api_key, field, value)
    await db.flush()

    return {"ok": True, "data": _apikey_to_dict(api_key)}


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    api_key = await db.get(ApiKey, key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key no encontrada")
    api_key.is_active = False
    await db.flush()
    return {"ok": True}


def _apikey_to_dict(k: ApiKey) -> dict:
    return {
        "id": k.id,
        "name": k.name,
        "key_prefix": k.key_prefix,
        "description": k.description,
        "scopes": k.scopes,
        "is_active": k.is_active,
        "expires_at": k.expires_at.isoformat() if k.expires_at else None,
        "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        "usage_count": k.usage_count,
        "created_at": k.created_at.isoformat() if k.created_at else None,
    }


# ── Category management ────────────────────────────────────────
class CategoryCreate(BaseModel):
    key: str
    label: str
    icon: str | None = None
    sort_order: int = 0
    description: str | None = None


class CategoryUpdate(BaseModel):
    key: str | None = None
    label: str | None = None
    icon: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    description: str | None = None


@router.get("/categories")
async def list_admin_categories(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    result = await db.execute(
        select(Category).order_by(Category.sort_order, Category.label)
    )
    return {"ok": True, "data": [_cat_to_dict(c) for c in result.scalars().all()]}


@router.post("/categories", status_code=201)
async def create_category(
    body: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    import re
    key = re.sub(r"[^a-z0-9_]", "", body.key.lower().strip().replace(" ", "_"))
    if not key:
        raise HTTPException(status_code=400, detail="Key invalido")

    existing = await db.execute(select(Category).where(Category.key == key))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"La categoria '{key}' ya existe")

    cat = Category(
        key=key,
        label=body.label,
        icon=body.icon,
        sort_order=body.sort_order,
        description=body.description,
    )
    db.add(cat)
    await db.flush()
    return {"ok": True, "data": _cat_to_dict(cat)}


@router.put("/categories/{cat_id}")
async def update_category(
    cat_id: int,
    body: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    cat = await db.get(Category, cat_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")

    update_data = body.model_dump(exclude_unset=True)
    if "key" in update_data:
        import re
        update_data["key"] = re.sub(r"[^a-z0-9_]", "", update_data["key"].lower().strip().replace(" ", "_"))

    for field, value in update_data.items():
        setattr(cat, field, value)
    await db.flush()
    return {"ok": True, "data": _cat_to_dict(cat)}


@router.delete("/categories/{cat_id}")
async def delete_category(
    cat_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    cat = await db.get(Category, cat_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")
    await db.delete(cat)
    await db.flush()
    return {"ok": True}


# ── Unit of measure management ─────────────────────────────────
class UomCreate(BaseModel):
    key: str
    label: str
    aliases: list[str] | None = None
    sort_order: int = 0


class UomUpdate(BaseModel):
    key: str | None = None
    label: str | None = None
    aliases: list[str] | None = None
    sort_order: int | None = None
    is_active: bool | None = None


@router.get("/uoms")
async def list_admin_uoms(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    result = await db.execute(
        select(UnitOfMeasure).order_by(UnitOfMeasure.sort_order, UnitOfMeasure.label)
    )
    return {"ok": True, "data": [_uom_to_dict(u) for u in result.scalars().all()]}


@router.post("/uoms", status_code=201)
async def create_uom(
    body: UomCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    import re
    key = re.sub(r"[^a-z0-9_]", "", body.key.lower().strip())
    if not key:
        raise HTTPException(status_code=400, detail="Key invalido")

    existing = await db.execute(select(UnitOfMeasure).where(UnitOfMeasure.key == key))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"La unidad '{key}' ya existe")

    uom = UnitOfMeasure(
        key=key,
        label=body.label,
        aliases=body.aliases,
        sort_order=body.sort_order,
    )
    db.add(uom)
    await db.flush()
    await _refresh_uom_cache(db)
    return {"ok": True, "data": _uom_to_dict(uom)}


@router.put("/uoms/{uom_id}")
async def update_uom(
    uom_id: int,
    body: UomUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    uom = await db.get(UnitOfMeasure, uom_id)
    if not uom:
        raise HTTPException(status_code=404, detail="Unidad no encontrada")

    update_data = body.model_dump(exclude_unset=True)
    if "key" in update_data:
        import re
        update_data["key"] = re.sub(r"[^a-z0-9_]", "", update_data["key"].lower().strip())

    for field, value in update_data.items():
        setattr(uom, field, value)
    await db.flush()
    await _refresh_uom_cache(db)
    return {"ok": True, "data": _uom_to_dict(uom)}


@router.delete("/uoms/{uom_id}")
async def delete_uom(
    uom_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    uom = await db.get(UnitOfMeasure, uom_id)
    if not uom:
        raise HTTPException(status_code=404, detail="Unidad no encontrada")
    await db.delete(uom)
    await db.flush()
    await _refresh_uom_cache(db)
    return {"ok": True}


async def _refresh_uom_cache(db: AsyncSession):
    """Rebuild matching engine UOM cache after admin changes."""
    from app.services.matching import build_uom_map_from_db
    await build_uom_map_from_db(db)


# ── Public catalog endpoints (no auth) ─────────────────────────
@router.get("/catalog/categories")
async def public_categories(db: AsyncSession = Depends(get_db)):
    """List active categories — public, no auth required."""
    result = await db.execute(
        select(Category)
        .where(Category.is_active == True)
        .order_by(Category.sort_order, Category.label)
    )
    return {"ok": True, "data": [_cat_to_dict(c) for c in result.scalars().all()]}


@router.get("/catalog/uoms")
async def public_uoms(db: AsyncSession = Depends(get_db)):
    """List active units of measure — public, no auth required."""
    result = await db.execute(
        select(UnitOfMeasure)
        .where(UnitOfMeasure.is_active == True)
        .order_by(UnitOfMeasure.sort_order, UnitOfMeasure.label)
    )
    return {"ok": True, "data": [_uom_to_dict(u) for u in result.scalars().all()]}


# ── Supplier search (for merge UI) ─────────────────────────────
@router.get("/suppliers/search")
async def admin_search_suppliers(
    q: str = Query("", min_length=0),
    limit: int = Query(15, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Busqueda rapida de proveedores por nombre/NIT para el modal de fusion."""
    query = select(Supplier).where(Supplier.is_active == True)
    if q.strip():
        pattern = f"%{q.strip()}%"
        query = query.where(
            Supplier.name.ilike(pattern)
            | Supplier.trade_name.ilike(pattern)
            | Supplier.nit.ilike(pattern)
        )
    query = query.order_by(Supplier.name).limit(limit)
    result = await db.execute(query)
    return {
        "ok": True,
        "data": [
            {
                "id": s.id,
                "name": s.name,
                "trade_name": s.trade_name,
                "nit": s.nit,
                "city": s.city,
                "department": s.department,
                "whatsapp": s.whatsapp,
                "verification_state": s.verification_state,
            }
            for s in result.scalars().all()
        ],
    }


@router.get("/suppliers/duplicate-suggestions")
async def duplicate_suggestions(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Sugiere pares de proveedores que podrian ser duplicados (nombre similar)."""
    # Use pg_trgm similarity if available, fallback to simple substring match
    try:
        pairs = await db.execute(text("""
            SELECT a.id as id_a, a.name as name_a, a.trade_name as trade_a,
                   a.city as city_a, a.nit as nit_a,
                   b.id as id_b, b.name as name_b, b.trade_name as trade_b,
                   b.city as city_b, b.nit as nit_b,
                   similarity(lower(a.name), lower(b.name)) as sim
            FROM mkt_supplier a
            JOIN mkt_supplier b ON a.id < b.id
            WHERE a.is_active = true AND b.is_active = true
              AND similarity(lower(a.name), lower(b.name)) > 0.3
            ORDER BY sim DESC
            LIMIT :lim
        """), {"lim": limit})
        rows = pairs.all()
    except Exception:
        # pg_trgm not available — fallback: match by same NIT or exact trade_name
        pairs = await db.execute(text("""
            SELECT a.id as id_a, a.name as name_a, a.trade_name as trade_a,
                   a.city as city_a, a.nit as nit_a,
                   b.id as id_b, b.name as name_b, b.trade_name as trade_b,
                   b.city as city_b, b.nit as nit_b,
                   0.5 as sim
            FROM mkt_supplier a
            JOIN mkt_supplier b ON a.id < b.id
            WHERE a.is_active = true AND b.is_active = true
              AND (
                (a.nit IS NOT NULL AND a.nit != '' AND a.nit = b.nit)
                OR lower(a.name) = lower(b.name)
                OR (a.trade_name IS NOT NULL AND lower(a.trade_name) = lower(b.trade_name))
              )
            ORDER BY a.name
            LIMIT :lim
        """), {"lim": limit})
        rows = pairs.all()

    return {
        "ok": True,
        "data": [
            {
                "supplier_a": {"id": r.id_a, "name": r.name_a, "trade_name": r.trade_a, "city": r.city_a, "nit": r.nit_a},
                "supplier_b": {"id": r.id_b, "name": r.name_b, "trade_name": r.trade_b, "city": r.city_b, "nit": r.nit_b},
                "similarity": round(float(r.sim), 2),
            }
            for r in rows
        ],
    }


# ── Supplier merge ─────────────────────────────────────────────
MERGE_FIELDS = [
    "name", "trade_name", "nit", "email", "phone", "whatsapp",
    "city", "department", "address", "website", "latitude", "longitude",
    "preferred_channel",
]


def _supplier_summary(s: Supplier) -> dict:
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
        "website": s.website,
        "latitude": s.latitude,
        "longitude": s.longitude,
        "categories": s.categories or [],
        "preferred_channel": s.preferred_channel,
        "verification_state": s.verification_state,
        "rating": s.rating,
        "quotation_count": s.quotation_count,
        "is_active": s.is_active,
    }


@router.get("/suppliers/merge-preview")
async def merge_preview(
    keep_id: int = Query(...),
    absorb_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Preview de fusion: muestra ambos proveedores y conteos de registros."""
    if keep_id == absorb_id:
        raise HTTPException(status_code=400, detail="No se puede fusionar un proveedor consigo mismo")

    keep = await db.get(Supplier, keep_id)
    absorb = await db.get(Supplier, absorb_id)
    if not keep:
        raise HTTPException(status_code=404, detail=f"Proveedor {keep_id} no encontrado")
    if not absorb:
        raise HTTPException(status_code=404, detail=f"Proveedor {absorb_id} no encontrado")

    # Count related records for absorb supplier
    branches = (await db.execute(
        select(func.count()).where(SupplierBranch.supplier_id == absorb_id)
    )).scalar() or 0
    quotations = (await db.execute(
        select(func.count()).where(Quotation.supplier_id == absorb_id)
    )).scalar() or 0
    matches = (await db.execute(
        select(func.count()).where(ProductMatch.supplier_id == absorb_id)
    )).scalar() or 0
    prices = (await db.execute(
        select(func.count()).where(PriceHistory.supplier_id == absorb_id)
    )).scalar() or 0

    return {
        "ok": True,
        "data": {
            "keep": _supplier_summary(keep),
            "absorb": _supplier_summary(absorb),
            "absorb_counts": {
                "branches": branches,
                "quotations": quotations,
                "product_matches": matches,
                "price_history": prices,
            },
        },
    }


class SupplierMergeRequest(BaseModel):
    keep_id: int
    absorb_id: int
    field_overrides: dict[str, str] = {}  # campo -> "keep" | "absorb"


@router.post("/suppliers/merge")
async def merge_suppliers(
    body: SupplierMergeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Fusionar dos proveedores. keep_id sobrevive, absorb_id se desactiva."""
    from datetime import datetime, timezone

    if body.keep_id == body.absorb_id:
        raise HTTPException(status_code=400, detail="No se puede fusionar un proveedor consigo mismo")

    keep = await db.get(Supplier, body.keep_id)
    absorb = await db.get(Supplier, body.absorb_id)
    if not keep:
        raise HTTPException(status_code=404, detail=f"Proveedor {body.keep_id} no encontrado")
    if not absorb:
        raise HTTPException(status_code=404, detail=f"Proveedor {body.absorb_id} no encontrado")

    summary = {}

    # 1. Apply field overrides
    overridden = []
    for field, choice in body.field_overrides.items():
        if field not in MERGE_FIELDS:
            continue
        if choice == "absorb":
            setattr(keep, field, getattr(absorb, field))
            overridden.append(field)
    summary["fields_overridden"] = overridden

    # 2. Merge categories (union, no duplicates)
    keep_cats = set(keep.categories or [])
    absorb_cats = set(absorb.categories or [])
    keep.categories = sorted(keep_cats | absorb_cats)

    # 3. Migrate branches
    result = await db.execute(
        select(SupplierBranch).where(SupplierBranch.supplier_id == body.absorb_id)
    )
    migrated_branches = result.scalars().all()
    for branch in migrated_branches:
        branch.supplier_id = body.keep_id
    summary["branches_migrated"] = len(migrated_branches)

    # 4. Migrate quotations
    q_result = await db.execute(
        select(Quotation).where(Quotation.supplier_id == body.absorb_id)
    )
    migrated_quotations = q_result.scalars().all()
    for q in migrated_quotations:
        q.supplier_id = body.keep_id
    summary["quotations_migrated"] = len(migrated_quotations)

    # 5. Migrate price history
    ph_result = await db.execute(
        select(PriceHistory).where(PriceHistory.supplier_id == body.absorb_id)
    )
    migrated_prices = ph_result.scalars().all()
    for ph in migrated_prices:
        ph.supplier_id = body.keep_id
    summary["price_history_migrated"] = len(migrated_prices)

    # 6. Migrate product matches (handle unique constraint conflicts)
    pm_result = await db.execute(
        select(ProductMatch).where(ProductMatch.supplier_id == body.absorb_id)
    )
    absorb_matches = pm_result.scalars().all()
    migrated_matches = 0
    merged_matches = 0
    for pm in absorb_matches:
        # Check for conflict with existing match on keep supplier
        conflict = (await db.execute(
            select(ProductMatch).where(
                ProductMatch.supplier_id == body.keep_id,
                ProductMatch.product_name_normalized == pm.product_name_normalized,
                ProductMatch.insumo_id == pm.insumo_id,
            )
        )).scalar_one_or_none()

        if conflict:
            # Merge: keep the one with higher confidence, sum usage_count
            conflict.usage_count += pm.usage_count
            if pm.confidence > conflict.confidence:
                conflict.confidence = pm.confidence
                conflict.method = pm.method
            if pm.is_validated and not conflict.is_validated:
                conflict.is_validated = True
                conflict.validated_by = pm.validated_by
            await db.delete(pm)
            merged_matches += 1
        else:
            pm.supplier_id = body.keep_id
            migrated_matches += 1
    summary["product_matches_migrated"] = migrated_matches
    summary["product_matches_merged"] = merged_matches

    # 7. Update RFQ supplier_ids arrays
    rfq_result = await db.execute(select(RFQ))
    rfqs_updated = 0
    for rfq in rfq_result.scalars().all():
        if rfq.supplier_ids and body.absorb_id in rfq.supplier_ids:
            new_ids = [body.keep_id if sid == body.absorb_id else sid for sid in rfq.supplier_ids]
            # Remove duplicates while preserving order
            seen = set()
            unique_ids = []
            for sid in new_ids:
                if sid not in seen:
                    seen.add(sid)
                    unique_ids.append(sid)
            rfq.supplier_ids = unique_ids
            rfqs_updated += 1
    summary["rfqs_updated"] = rfqs_updated

    # 8. Sum stats
    keep.quotation_count = (keep.quotation_count or 0) + (absorb.quotation_count or 0)

    # 9. Handle user association
    if absorb.user_id:
        summary["user_disassociated"] = absorb.user_id
        absorb.user_id = None

    # 10. Soft-delete absorbed supplier
    absorb.is_active = False
    absorb.extra_data = {
        **(absorb.extra_data or {}),
        "merged_into": body.keep_id,
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "merged_by": user.id,
    }

    await db.commit()

    return {
        "ok": True,
        "data": {
            "keep_id": body.keep_id,
            "absorb_id": body.absorb_id,
            "summary": summary,
        },
    }


# ── Helpers ────────────────────────────────────────────────────
def _cat_to_dict(c: Category) -> dict:
    return {
        "id": c.id,
        "key": c.key,
        "label": c.label,
        "icon": c.icon,
        "sort_order": c.sort_order,
        "is_active": c.is_active,
        "description": c.description,
    }


def _uom_to_dict(u: UnitOfMeasure) -> dict:
    return {
        "id": u.id,
        "key": u.key,
        "label": u.label,
        "aliases": u.aliases or [],
        "sort_order": u.sort_order,
        "is_active": u.is_active,
    }


def _user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role,
        "is_active": u.is_active,
        "phone": u.phone,
        "company_name": u.company_name,
        "company_id": getattr(u, 'company_id', None),
        "company_role": getattr(u, 'company_role', None),
        "last_login": u.last_login.isoformat() if u.last_login else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


# ── Supplier suggestions admin ────────────────────────────────
from app.models.supplier_suggestion import SupplierSuggestion


@router.get("/supplier-suggestions")
async def admin_list_suggestions(
    state_filter: str | None = Query(None, alias="state"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Listar sugerencias de proveedores."""
    query = select(SupplierSuggestion)
    if state_filter:
        query = query.where(SupplierSuggestion.state == state_filter)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(
        query.order_by(SupplierSuggestion.created_at.desc()).offset(offset).limit(limit)
    )
    suggestions = result.scalars().all()
    return {
        "ok": True,
        "data": [_sugg_to_dict(s) for s in suggestions],
        "total": total,
    }


@router.put("/supplier-suggestions/{sugg_id}/approve")
async def approve_suggestion(
    sugg_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Aprobar sugerencia y crear proveedor."""
    from datetime import datetime, timezone

    sugg = await db.get(SupplierSuggestion, sugg_id)
    if not sugg:
        raise HTTPException(404, "Sugerencia no encontrada")
    if sugg.state != "pending":
        raise HTTPException(400, f"Esta sugerencia ya fue procesada ({sugg.state})")

    # Create supplier
    supplier = Supplier(
        name=sugg.name,
        trade_name=sugg.trade_name,
        nit=sugg.nit,
        email=sugg.email,
        phone=sugg.phone,
        whatsapp=sugg.whatsapp,
        city=sugg.city,
        department=sugg.department,
        address=sugg.address,
        categories=sugg.categories,
        verification_state="verified",
    )
    db.add(supplier)
    await db.flush()

    sugg.state = "approved"
    sugg.reviewed_by = user.id
    sugg.reviewed_at = datetime.now(timezone.utc)
    sugg.created_supplier_id = supplier.id

    if sugg.suggested_by:
        from app.services.notifications import notify_suggestion_approved
        await notify_suggestion_approved(db, sugg.suggested_by, sugg.name)

    await db.commit()

    return {"ok": True, "data": {"suggestion_id": sugg.id, "supplier_id": supplier.id}}


@router.put("/supplier-suggestions/{sugg_id}/reject")
async def reject_suggestion(
    sugg_id: int,
    reason: str = Query("", alias="reason"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Rechazar sugerencia."""
    from datetime import datetime, timezone

    sugg = await db.get(SupplierSuggestion, sugg_id)
    if not sugg:
        raise HTTPException(404, "Sugerencia no encontrada")
    if sugg.state != "pending":
        raise HTTPException(400, f"Esta sugerencia ya fue procesada ({sugg.state})")

    sugg.state = "rejected"
    sugg.reviewed_by = user.id
    sugg.reviewed_at = datetime.now(timezone.utc)
    sugg.review_notes = reason or None
    await db.commit()

    return {"ok": True}


def _sugg_to_dict(s: SupplierSuggestion) -> dict:
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
        "categories": s.categories or [],
        "notes": s.notes,
        "state": s.state,
        "suggested_by": s.suggested_by,
        "suggester_name": s.suggester.full_name if s.suggester else None,
        "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None,
        "review_notes": s.review_notes,
        "created_supplier_id": s.created_supplier_id,
        "created_at": s.created_at.isoformat(),
    }


# ── Company admin ─────────────────────────────────────────────
from app.models.company import Company, Subscription, Plan
from app.core.plans import PLANS, get_plan_limits, refresh_plans_cache


@router.get("/companies")
async def admin_list_companies(
    q: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    query = select(Company)
    if q:
        query = query.where(
            Company.name.ilike(f"%{q}%") | Company.nit.ilike(f"%{q}%")
        )
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(query.order_by(Company.created_at.desc()).offset(offset).limit(limit))
    companies = result.scalars().all()

    data = []
    for c in companies:
        d = {
            "id": c.id,
            "name": c.name,
            "nit": c.nit,
            "city": c.city,
            "department": c.department,
            "industry": c.industry,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat(),
        }
        # Get subscription
        sub = (await db.execute(
            select(Subscription).where(Subscription.company_id == c.id)
        )).scalar_one_or_none()
        if sub:
            d["plan"] = sub.plan
            d["sub_state"] = sub.state
            d["max_users"] = sub.max_users
            d["expires_at"] = sub.expires_at.isoformat() if sub.expires_at else None
        # Member count
        d["member_count"] = (await db.execute(
            select(func.count(User.id)).where(User.company_id == c.id)
        )).scalar() or 0
        data.append(d)

    return {"ok": True, "data": data, "total": total}


@router.get("/subscriptions")
async def admin_list_subscriptions(
    plan: str | None = Query(None),
    state: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    query = select(Subscription)
    if plan:
        query = query.where(Subscription.plan == plan)
    if state:
        query = query.where(Subscription.state == state)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(
        query.order_by(Subscription.created_at.desc()).offset(offset).limit(limit)
    )
    subs = result.scalars().all()

    data = []
    for s in subs:
        company = await db.get(Company, s.company_id)
        data.append({
            "id": s.id,
            "company_id": s.company_id,
            "company_name": company.name if company else None,
            "plan": s.plan,
            "state": s.state,
            "max_users": s.max_users,
            "max_pedidos_month": s.max_pedidos_month,
            "started_at": s.started_at.isoformat(),
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "payment_method": s.payment_method,
            "last_payment_date": s.last_payment_date.isoformat() if s.last_payment_date else None,
            "last_payment_amount": s.last_payment_amount,
            "notes": s.notes,
        })
    return {"ok": True, "data": data, "total": total}


class SubscriptionAdminUpdate(BaseModel):
    plan: str | None = None
    state: str | None = None
    max_users: int | None = None
    max_pedidos_month: int | None = None
    payment_method: str | None = None
    last_payment_amount: float | None = None
    last_payment_ref: str | None = None
    expires_at: str | None = None  # ISO format
    notes: str | None = None


@router.put("/subscriptions/{sub_id}")
async def admin_update_subscription(
    sub_id: int,
    body: SubscriptionAdminUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Activar/modificar suscripcion (billing manual)."""
    sub = await db.get(Subscription, sub_id)
    if not sub:
        raise HTTPException(404, "Suscripcion no encontrada")

    data = body.model_dump(exclude_unset=True)

    if "plan" in data and data["plan"]:
        if data["plan"] not in PLANS:
            raise HTTPException(400, f"Plan invalido: {', '.join(PLANS.keys())}")
        max_u, max_p = get_plan_limits(data["plan"])
        sub.plan = data.pop("plan")
        if "max_users" not in data:
            sub.max_users = max_u
        if "max_pedidos_month" not in data:
            sub.max_pedidos_month = max_p

    if "expires_at" in data:
        from datetime import datetime
        if data["expires_at"]:
            sub.expires_at = datetime.fromisoformat(data.pop("expires_at"))
        else:
            sub.expires_at = None
            data.pop("expires_at")

    if "last_payment_amount" in data and data["last_payment_amount"]:
        from datetime import date
        sub.last_payment_date = date.today()

    for k, v in data.items():
        if hasattr(sub, k):
            setattr(sub, k, v)

    # Notify company admin about subscription change
    from app.services.notifications import notify_subscription_updated
    company = await db.get(Company, sub.company_id)
    if company:
        admin_result = await db.execute(
            select(User).where(User.company_id == sub.company_id, User.company_role == "company_admin")
        )
        for ca in admin_result.scalars().all():
            plan_label = PLANS.get(sub.plan, {}).get("label", sub.plan)
            await notify_subscription_updated(db, ca.id, plan_label)

    await db.commit()
    await db.refresh(sub)

    plan_info = PLANS.get(sub.plan, {})
    return {
        "ok": True,
        "data": {
            "id": sub.id,
            "company_id": sub.company_id,
            "plan": sub.plan,
            "plan_label": plan_info.get("label", sub.plan),
            "state": sub.state,
            "max_users": sub.max_users,
            "max_pedidos_month": sub.max_pedidos_month,
            "started_at": sub.started_at.isoformat(),
            "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
            "payment_method": sub.payment_method,
            "last_payment_date": sub.last_payment_date.isoformat() if sub.last_payment_date else None,
            "last_payment_amount": sub.last_payment_amount,
            "notes": sub.notes,
        },
    }


# ── Plan management ───────────────────────────────────────────
class PlanCreate(BaseModel):
    key: str
    label: str
    max_users: int = 1
    max_pedidos_month: int = 5
    price_bob: float = 0
    features: list[str] | None = None
    sort_order: int = 0


class PlanUpdate(BaseModel):
    label: str | None = None
    max_users: int | None = None
    max_pedidos_month: int | None = None
    price_bob: float | None = None
    features: list[str] | None = None
    sort_order: int | None = None
    is_active: bool | None = None


@router.get("/plans")
async def admin_list_plans(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Listar todos los planes (incluye inactivos)."""
    result = await db.execute(select(Plan).order_by(Plan.sort_order))
    plans = result.scalars().all()
    return {"ok": True, "data": [p.to_dict() for p in plans]}


@router.post("/plans", status_code=201)
async def admin_create_plan(
    body: PlanCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    import re
    key = re.sub(r"[^a-z0-9_]", "", body.key.lower().strip().replace(" ", "_"))
    if not key:
        raise HTTPException(400, "Key invalido")

    existing = await db.execute(select(Plan).where(Plan.key == key))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"El plan '{key}' ya existe")

    plan = Plan(
        key=key,
        label=body.label,
        max_users=body.max_users,
        max_pedidos_month=body.max_pedidos_month,
        price_bob=body.price_bob,
        features=body.features,
        sort_order=body.sort_order,
    )
    db.add(plan)
    await db.commit()
    await refresh_plans_cache(db)
    return {"ok": True, "data": plan.to_dict()}


@router.put("/plans/{plan_id}")
async def admin_update_plan(
    plan_id: int,
    body: PlanUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    plan = await db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan no encontrado")

    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(plan, k, v)
    await db.commit()
    await refresh_plans_cache(db)
    return {"ok": True, "data": plan.to_dict()}


@router.delete("/plans/{plan_id}")
async def admin_delete_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    plan = await db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan no encontrado")

    # Check if any subscription uses this plan
    in_use = (await db.execute(
        select(func.count()).where(Subscription.plan == plan.key)
    )).scalar() or 0
    if in_use:
        raise HTTPException(400, f"No se puede eliminar: {in_use} suscripcion(es) usan este plan. Desactivalo en su lugar.")

    await db.delete(plan)
    await db.commit()
    await refresh_plans_cache(db)
    return {"ok": True}


# ── Scheduled Tasks (Cron Jobs) ─────────────────────────────────
from app.models.task_log import TaskLog


@router.get("/tasks/jobs")
async def list_jobs(user: User = Depends(require_admin)):
    """Listar jobs programados con su estado."""
    from app.core.scheduler import JOB_REGISTRY, scheduler

    jobs = []
    for name, info in JOB_REGISTRY.items():
        ap_job = scheduler.get_job(name)
        next_run = None
        if ap_job and ap_job.next_run_time:
            next_run = ap_job.next_run_time.isoformat()
        jobs.append({
            "name": info["name"],
            "label": info["label"],
            "cron": info["cron"],
            "description": info["description"],
            "next_run": next_run,
        })
    return {"ok": True, "data": jobs}


@router.get("/tasks/logs")
async def list_task_logs(
    job_name: str = Query(None),
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Historial de ejecuciones de tareas."""
    q = select(TaskLog).order_by(TaskLog.started_at.desc())
    if job_name:
        q = q.where(TaskLog.job_name == job_name)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    logs = result.scalars().all()

    return {
        "ok": True,
        "data": [
            {
                "id": l.id,
                "job_name": l.job_name,
                "state": l.state,
                "started_at": l.started_at.isoformat() if l.started_at else None,
                "finished_at": l.finished_at.isoformat() if l.finished_at else None,
                "duration_s": l.duration_s,
                "result_summary": l.result_summary,
                "result_data": l.result_data,
                "error": l.error,
            }
            for l in logs
        ],
    }


@router.post("/tasks/{job_name}/run")
async def run_job_now(
    job_name: str,
    user: User = Depends(require_admin),
):
    """Ejecutar un job manualmente (ahora mismo)."""
    from app.core.scheduler import JOB_REGISTRY, execute_job

    if job_name not in JOB_REGISTRY:
        raise HTTPException(404, f"Job no encontrado: {job_name}")

    result = await execute_job(job_name)
    return {"ok": True, "data": result}


# ── AI Config (System-wide) ─────────────────────────────────────
from app.models.system_setting import SystemSetting
from app.core.ai_providers import get_all_providers


@router.get("/ai-config")
async def get_ai_config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Obtener config AI del sistema + lista de proveedores."""
    setting = await db.get(SystemSetting, "ai_config")
    current = setting.value if setting else None

    return {
        "ok": True,
        "data": {
            "config": current,
            "providers": get_all_providers(),
        },
    }


class AIConfigUpdate(BaseModel):
    provider: str
    api_key: str
    model: str = ""


@router.put("/ai-config")
async def update_ai_config(
    body: AIConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Guardar config AI del sistema."""
    from app.core.ai_providers import get_provider_info
    provider_info = get_provider_info(body.provider)
    if not provider_info:
        raise HTTPException(400, f"Proveedor no valido: {body.provider}")

    config_data = {
        "provider": body.provider,
        "api_key": body.api_key,
        "model": body.model or provider_info["default_model"],
        "api_format": provider_info["api_format"],
        "base_url": provider_info["base_url"],
    }

    setting = await db.get(SystemSetting, "ai_config")
    if setting:
        setting.value = config_data
        sa_attrs.flag_modified(setting, "value")
    else:
        setting = SystemSetting(key="ai_config", value=config_data)
        db.add(setting)

    await db.commit()
    return {"ok": True, "data": config_data}


@router.post("/ai-config/test")
async def test_ai_config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Probar la config AI del sistema enviando un prompt simple."""
    from app.services.ai_extract import resolve_ai_config
    config = await resolve_ai_config()
    if not config or not config.get("api_key"):
        return {"ok": False, "error": "No hay config de IA configurada"}

    try:
        result = await _test_ai_call(config)
        return {"ok": True, "data": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _test_ai_call(config: dict) -> dict:
    """Hace una llamada minima de prueba al proveedor AI."""
    import httpx

    prompt = "Responde solo con el JSON: {\"status\": \"ok\", \"model\": \"tu nombre de modelo\"}"

    if config["api_format"] == "anthropic":
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                config["base_url"],
                headers={
                    "x-api-key": config["api_key"],
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config["model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 100,
                },
            )
    else:
        url = config["base_url"].rstrip("/")
        if config["api_format"] == "openrouter":
            endpoint = url
        else:
            endpoint = f"{url}/chat/completions" if not url.endswith("/chat/completions") else url

        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                endpoint,
                headers=headers,
                json={
                    "model": config["model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 100,
                },
            )

    if resp.status_code != 200:
        raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")

    return {
        "provider": config["provider"],
        "model": config["model"],
        "status_code": resp.status_code,
        "response_preview": resp.text[:300],
    }


# ── SEO / Site Config ───────────────────────────────────────────

@router.get("/seo-config")
async def get_seo_config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Obtener config SEO del sitio con defaults."""
    from app.main import SEO_DEFAULTS
    setting = await db.get(SystemSetting, "seo_config")
    config = dict(SEO_DEFAULTS)
    if setting and setting.value:
        config.update(setting.value)
    return {"ok": True, "data": config}


@router.put("/seo-config")
async def update_seo_config(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Guardar config SEO del sitio."""
    allowed_keys = {
        "site_name", "site_title", "site_description", "site_keywords",
        "og_image", "theme_color", "footer_text", "analytics_id",
        "contact_email", "contact_whatsapp",
    }
    config = {k: v for k, v in body.items() if k in allowed_keys}

    setting = await db.get(SystemSetting, "seo_config")
    if setting:
        setting.value = config
        sa_attrs.flag_modified(setting, "value")
    else:
        setting = SystemSetting(key="seo_config", value=config)
        db.add(setting)

    await db.commit()
    return {"ok": True, "data": config}


# ── Integrations config (WhatsApp / Telegram / SMTP) ──────────

@router.get("/integrations")
async def get_integrations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Return current integration config (masking secrets)."""
    setting = await db.get(SystemSetting, "integrations")
    cfg = setting.value if setting and setting.value else {}

    # Merge with env-based defaults
    from app.core.config import settings as env
    defaults = {
        "evolution_api_url": env.evolution_api_url,
        "evolution_api_key": env.evolution_api_key,
        "evolution_instance_name": env.evolution_instance_name,
        "telegram_bot_token": env.telegram_bot_token,
        "telegram_webhook_secret": env.telegram_webhook_secret,
        "smtp_host": env.smtp_host,
        "smtp_port": env.smtp_port,
        "smtp_user": env.smtp_user,
        "smtp_password": env.smtp_password,
        "smtp_from": env.smtp_from,
    }
    merged = {**defaults, **cfg}

    # Mask secrets for display
    display = dict(merged)
    for k in ("evolution_api_key", "telegram_bot_token", "smtp_password"):
        val = display.get(k, "")
        if val and len(val) > 6:
            display[k + "_masked"] = val[:3] + "***" + val[-3:]
        else:
            display[k + "_masked"] = "***" if val else ""

    # Evolution instances (multi-instance support)
    instances = cfg.get("evolution_instances", [])
    display_instances = []
    for inst in instances:
        di = dict(inst)
        ak = di.get("api_key", "")
        if ak and len(ak) > 6:
            di["api_key_masked"] = ak[:3] + "***" + ak[-3:]
        else:
            di["api_key_masked"] = "***" if ak else ""
        display_instances.append(di)
    display["evolution_instances"] = display_instances

    # Public URL (for webhooks)
    public_url = (cfg.get("public_url") or env.app_url).rstrip("/")
    display["public_url"] = cfg.get("public_url", "")  # only show DB-saved value

    # Build webhook URLs using public URL
    display["webhook_whatsapp"] = f"{public_url}/api/v1/webhook/whatsapp"
    display["webhook_telegram"] = f"{public_url}/api/v1/webhook/telegram"
    if merged.get("telegram_webhook_secret"):
        display["webhook_telegram"] += f"?secret={merged['telegram_webhook_secret']}"

    # Bot authorized users
    bot_setting = await db.get(SystemSetting, "bot_authorized_users")
    display["bot_authorized"] = bot_setting.value if bot_setting and bot_setting.value else {
        "telegram": [], "whatsapp": []
    }

    # Routine config (mask token)
    routine_setting = await db.get(SystemSetting, "routine_config")
    if routine_setting and routine_setting.value:
        rc = routine_setting.value
        display["routine_config"] = {
            "routine_id": rc.get("routine_id", ""),
            "token_set": bool(rc.get("token")),
        }
    else:
        display["routine_config"] = {"routine_id": "", "token_set": False}

    return {"ok": True, "data": display}


@router.put("/integrations")
async def update_integrations(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Update integration config."""
    allowed_keys = {
        "public_url",
        "evolution_api_url", "evolution_api_key", "evolution_instance_name",
        "telegram_bot_token", "telegram_webhook_secret",
        "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from",
    }
    config = {k: v for k, v in body.items() if k in allowed_keys and v != ""}

    setting = await db.get(SystemSetting, "integrations")
    if setting:
        current = setting.value or {}
        current.update(config)
    else:
        current = config

    # Handle evolution_instances array
    if "evolution_instances" in body and isinstance(body["evolution_instances"], list):
        import uuid as _uuid
        instances = []
        for inst in body["evolution_instances"]:
            if not isinstance(inst, dict):
                continue
            entry = {
                "id": inst.get("id") or str(_uuid.uuid4())[:8],
                "label": inst.get("label", "").strip(),
                "url": inst.get("url", "").strip().rstrip("/"),
                "api_key": inst.get("api_key", "").strip(),
                "instance_name": inst.get("instance_name", "default").strip(),
                "is_default": bool(inst.get("is_default", False)),
            }
            if entry["url"] and entry["api_key"]:
                instances.append(entry)
        # Ensure exactly one default
        if instances and not any(i["is_default"] for i in instances):
            instances[0]["is_default"] = True
        current["evolution_instances"] = instances

    if setting:
        setting.value = current
        sa_attrs.flag_modified(setting, "value")
    else:
        setting = SystemSetting(key="integrations", value=current)
        db.add(setting)

    # Handle routine config
    if "routine_id" in body or "routine_token" in body:
        routine_setting = await db.get(SystemSetting, "routine_config")
        routine_data = routine_setting.value if routine_setting and routine_setting.value else {}
        if body.get("routine_id"):
            routine_data["routine_id"] = body["routine_id"]
        if body.get("routine_token"):
            routine_data["token"] = body["routine_token"]
        routine_data["token_set"] = bool(routine_data.get("token"))
        if routine_setting:
            routine_setting.value = routine_data
            sa_attrs.flag_modified(routine_setting, "value")
        else:
            routine_setting = SystemSetting(key="routine_config", value=routine_data)
            db.add(routine_setting)

    # Handle bot authorized users separately
    if "bot_authorized" in body and isinstance(body["bot_authorized"], dict):
        bot_data = {
            "telegram": [s.strip() for s in body["bot_authorized"].get("telegram", []) if s.strip()],
            "whatsapp": [s.strip() for s in body["bot_authorized"].get("whatsapp", []) if s.strip()],
        }
        bot_setting = await db.get(SystemSetting, "bot_authorized_users")
        if bot_setting:
            bot_setting.value = bot_data
            sa_attrs.flag_modified(bot_setting, "value")
        else:
            bot_setting = SystemSetting(key="bot_authorized_users", value=bot_data)
            db.add(bot_setting)

    await db.commit()
    return {"ok": True, "data": config}


@router.post("/integrations/test-whatsapp")
async def test_whatsapp_connection(
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Test Evolution API connection by fetching instance status."""
    import httpx
    body = body or {}
    setting = await db.get(SystemSetting, "integrations")
    cfg = setting.value if setting and setting.value else {}

    from app.core.config import settings as env

    # Support testing a specific instance by id
    instance_id = body.get("instance_id")
    instances = cfg.get("evolution_instances", [])
    if instance_id and instances:
        inst = next((i for i in instances if i.get("id") == instance_id), None)
        if inst:
            url = inst.get("url", "").rstrip("/")
            api_key = inst.get("api_key", "")
            instance = inst.get("instance_name", "default")
        else:
            return {"ok": False, "error": f"Instancia '{instance_id}' no encontrada"}
    else:
        url = cfg.get("evolution_api_url") or env.evolution_api_url
        api_key = cfg.get("evolution_api_key") or env.evolution_api_key
        instance = cfg.get("evolution_instance_name") or env.evolution_instance_name

    if not url or not api_key:
        return {"ok": False, "error": "URL y API Key son requeridos"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{url.rstrip('/')}/instance/connectionState/{instance}",
                headers={"apikey": api_key},
            )
        if resp.status_code == 200:
            data = resp.json()
            state = data.get("instance", {}).get("state", data.get("state", "unknown"))
            return {"ok": True, "data": {"state": state, "instance": instance}}
        else:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.post("/integrations/setup-telegram-webhook")
async def setup_telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Register the Telegram webhook URL with Telegram Bot API."""
    import httpx
    setting = await db.get(SystemSetting, "integrations")
    cfg = setting.value if setting and setting.value else {}

    from app.core.config import settings as env
    token = cfg.get("telegram_bot_token") or env.telegram_bot_token
    secret = cfg.get("telegram_webhook_secret") or env.telegram_webhook_secret

    # Resolve public URL: DB config → APP_URL env → request origin
    app_url = cfg.get("public_url") or ""
    if not app_url or "localhost" in app_url or "127.0.0.1" in app_url:
        app_url = env.app_url
    if not app_url or "localhost" in app_url or "127.0.0.1" in app_url:
        # Last resort: derive from the incoming request (works behind reverse proxy)
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
        if host and "localhost" not in host and "127.0.0.1" not in host:
            app_url = f"{scheme}://{host}"

    app_url = app_url.rstrip("/")

    if not token:
        return {"ok": False, "error": "Bot token no configurado"}
    if not app_url or "localhost" in app_url or "127.0.0.1" in app_url:
        return {
            "ok": False,
            "error": (
                f"URL publica no configurada (actual: {app_url or 'vacio'}). "
                "Configura la 'URL Publica del Portal' en la seccion de Integraciones "
                "con tu dominio HTTPS (ej: https://apu-marketplace-app.q8waob.easypanel.host)"
            ),
        }
    if not app_url.startswith("https://"):
        return {"ok": False, "error": f"Telegram requiere HTTPS. URL actual: {app_url}"}

    webhook_url = f"{app_url}/api/v1/webhook/telegram"
    if secret:
        webhook_url += f"?secret={secret}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/setWebhook",
                json={
                    "url": webhook_url,
                    "allowed_updates": ["message"],
                },
            )
        data = resp.json()
        if data.get("ok"):
            return {"ok": True, "data": {"webhook_url": webhook_url, "description": data.get("description", "OK")}}
        else:
            return {"ok": False, "error": f"{data.get('description', 'Error desconocido')} (URL enviada: {webhook_url})"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.post("/integrations/test-telegram")
async def test_telegram_send(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Send a test message to a Telegram chat ID."""
    import httpx
    setting = await db.get(SystemSetting, "integrations")
    cfg = setting.value if setting and setting.value else {}

    from app.core.config import settings as env
    token = cfg.get("telegram_bot_token") or env.telegram_bot_token
    chat_id = body.get("chat_id", "")

    if not token:
        return {"ok": False, "error": "Bot token no configurado"}
    if not chat_id:
        return {"ok": False, "error": "chat_id requerido"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": "✅ Test desde APU Marketplace! El bot esta funcionando correctamente.",
                    "parse_mode": "HTML",
                },
            )
        data = resp.json()
        if data.get("ok"):
            return {"ok": True, "data": {"message_id": data["result"]["message_id"]}}
        else:
            return {"ok": False, "error": data.get("description", "Error")}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.post("/integrations/test-email")
async def test_email_connection(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Test SMTP connection."""
    import aiosmtplib
    setting = await db.get(SystemSetting, "integrations")
    cfg = setting.value if setting and setting.value else {}

    from app.core.config import settings as env
    host = cfg.get("smtp_host") or env.smtp_host
    port = cfg.get("smtp_port") or env.smtp_port
    smtp_user = cfg.get("smtp_user") or env.smtp_user
    smtp_pass = cfg.get("smtp_password") or env.smtp_password

    if not smtp_user or not smtp_pass:
        return {"ok": False, "error": "SMTP user y password son requeridos"}

    try:
        smtp = aiosmtplib.SMTP(hostname=host, port=port, use_tls=True)
        await smtp.connect()
        await smtp.login(smtp_user, smtp_pass)
        await smtp.quit()
        return {"ok": True, "data": {"host": host, "port": port, "user": smtp_user}}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.post("/integrations/test-routine")
async def test_routine(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Test Claude Code Routine connection."""
    from app.services.agent_executor import fire_routine
    result = await fire_routine(db, "Tarea de prueba: responde 'OK' y lista las herramientas disponibles.")
    if result.get("estado") == "iniciada":
        return {"ok": True, "data": {
            "session_id": result.get("mensaje", ""),
            "url": result.get("url", ""),
        }}
    else:
        return {"ok": False, "error": result.get("error", "Error desconocido")}


# ── AI Agents ──────────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str
    agent_type: str
    provider: str = ""
    model: str = ""
    api_key: str = ""
    system_prompt: str = ""
    channels: dict | None = None
    triggers: dict | None = None
    config: dict | None = None
    is_active: bool = True


class AgentUpdate(BaseModel):
    name: str | None = None
    agent_type: str | None = None
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    system_prompt: str | None = None
    channels: dict | None = None
    triggers: dict | None = None
    config: dict | None = None
    is_active: bool | None = None


@router.get("/agents")
async def list_agents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Listar todos los agentes AI configurados + tipos disponibles."""
    from app.core.ai_providers import get_all_agent_types, get_all_providers
    result = await db.execute(select(AIAgent).order_by(AIAgent.id))
    agents = result.scalars().all()

    agents_data = []
    for a in agents:
        agents_data.append({
            "id": a.id,
            "name": a.name,
            "agent_type": a.agent_type,
            "provider": a.provider or "",
            "model": a.model or "",
            "api_key_set": bool(a.api_key),
            "system_prompt": a.system_prompt or "",
            "channels": a.channels or {},
            "triggers": a.triggers or {},
            "config": a.config or {},
            "is_active": a.is_active,
        })

    return {
        "ok": True,
        "data": {
            "agents": agents_data,
            "agent_types": get_all_agent_types(),
            "providers": get_all_providers(),
        },
    }


@router.post("/agents")
async def create_agent(
    body: AgentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Crear un nuevo agente AI."""
    from app.core.ai_providers import get_agent_type
    if not get_agent_type(body.agent_type):
        raise HTTPException(400, f"Tipo de agente no valido: {body.agent_type}")

    agent = AIAgent(
        name=body.name,
        agent_type=body.agent_type,
        provider=body.provider or None,
        model=body.model or None,
        api_key=body.api_key or None,
        system_prompt=body.system_prompt or None,
        channels=body.channels,
        triggers=body.triggers,
        config=body.config,
        is_active=body.is_active,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    return {"ok": True, "data": {"id": agent.id, "name": agent.name}}


@router.put("/agents/{agent_id}")
async def update_agent(
    agent_id: int,
    body: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Actualizar un agente AI."""
    agent = await db.get(AIAgent, agent_id)
    if not agent:
        raise HTTPException(404, "Agente no encontrado")

    for field in ("name", "agent_type", "provider", "model", "system_prompt",
                  "channels", "triggers", "config", "is_active"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(agent, field, val)

    if body.api_key is not None:
        agent.api_key = body.api_key or None

    await db.commit()
    return {"ok": True, "data": {"id": agent.id, "name": agent.name}}


@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Eliminar un agente AI."""
    agent = await db.get(AIAgent, agent_id)
    if not agent:
        raise HTTPException(404, "Agente no encontrado")

    await db.delete(agent)
    await db.commit()
    return {"ok": True}


@router.post("/agents/{agent_id}/toggle")
async def toggle_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Activar/desactivar un agente."""
    agent = await db.get(AIAgent, agent_id)
    if not agent:
        raise HTTPException(404, "Agente no encontrado")

    agent.is_active = not agent.is_active
    await db.commit()
    return {"ok": True, "data": {"id": agent.id, "is_active": agent.is_active}}


@router.post("/agents/{agent_id}/test")
async def test_agent(
    agent_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Enviar un prompt de prueba al agente para verificar que funciona."""
    agent = await db.get(AIAgent, agent_id)
    if not agent:
        raise HTTPException(404, "Agente no encontrado")

    # Resolve AI config: agent-specific > global
    from app.core.ai_providers import get_provider_info
    from app.models.system_setting import SystemSetting

    provider_key = agent.provider
    api_key = agent.api_key
    model = agent.model

    # Fallback to global config
    if not provider_key or not api_key:
        global_setting = await db.get(SystemSetting, "ai_config")
        if global_setting and global_setting.value:
            gc = global_setting.value
            if not provider_key:
                provider_key = gc.get("provider", "")
            if not api_key:
                api_key = gc.get("api_key", "")
            if not model:
                model = gc.get("model", "")

    if not provider_key or not api_key:
        return {"ok": False, "error": "Agente sin proveedor/key configurado y sin config global"}

    provider_info = get_provider_info(provider_key)
    if not provider_info:
        return {"ok": False, "error": f"Proveedor no valido: {provider_key}"}

    config = {
        "api_format": provider_info["api_format"],
        "base_url": provider_info["base_url"],
        "api_key": api_key,
        "model": model or provider_info["default_model"],
    }

    try:
        result = await _test_ai_call(config)
        return {"ok": True, "data": {
            "provider": provider_key,
            "model": config["model"],
            "agent": agent.name,
            **result,
        }}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
