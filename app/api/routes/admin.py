from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password, verify_api_key
from app.api.deps import require_admin, require_manager, require_staff, STAFF_ROLES
from app.models.insumo import Insumo, InsumoRegionalPrice
from app.models.quotation import Quotation
from app.models.supplier import Supplier
from app.models.user import User

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


# ── Helpers ────────────────────────────────────────────────────
def _user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "full_name": u.full_name,
        "role": u.role,
        "is_active": u.is_active,
        "phone": u.phone,
        "company_name": u.company_name,
        "last_login": u.last_login.isoformat() if u.last_login else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }
