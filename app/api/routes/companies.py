"""Endpoints para empresas y equipo."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.plans import PLANS, get_plan_limits
from app.core.security import get_current_user
from app.models.company import Company, Subscription
from app.models.user import User
from app.models.pedido import Pedido

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────
class CompanyCreate(BaseModel):
    name: str
    nit: str | None = None
    industry: str | None = None
    city: str | None = None
    department: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None


class CompanyUpdate(BaseModel):
    name: str | None = None
    nit: str | None = None
    industry: str | None = None
    city: str | None = None
    department: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None


class MemberAdd(BaseModel):
    email: EmailStr
    company_role: str = "cotizador"  # company_admin, cotizador, viewer


class MemberUpdate(BaseModel):
    company_role: str


# ── Helpers ───────────────────────────────────────────────────
def _company_to_dict(c: Company) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "nit": c.nit,
        "industry": c.industry,
        "city": c.city,
        "department": c.department,
        "country": c.country,
        "address": c.address,
        "phone": c.phone,
        "email": c.email,
        "website": c.website,
        "logo_url": c.logo_url,
        "is_active": c.is_active,
        "created_at": c.created_at.isoformat(),
    }


def _subscription_to_dict(s: Subscription) -> dict:
    plan_info = PLANS.get(s.plan, {})
    return {
        "id": s.id,
        "company_id": s.company_id,
        "plan": s.plan,
        "plan_label": plan_info.get("label", s.plan),
        "state": s.state,
        "max_users": s.max_users,
        "max_pedidos_month": s.max_pedidos_month,
        "started_at": s.started_at.isoformat(),
        "expires_at": s.expires_at.isoformat() if s.expires_at else None,
        "payment_method": s.payment_method,
        "last_payment_date": s.last_payment_date.isoformat() if s.last_payment_date else None,
        "last_payment_amount": s.last_payment_amount,
    }


def _member_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "full_name": u.full_name,
        "company_role": u.company_role,
        "is_active": u.is_active,
        "last_login": u.last_login.isoformat() if u.last_login else None,
    }


def _require_company_admin(user: User):
    if not user.company_id:
        raise HTTPException(403, "No perteneces a una empresa")
    if user.company_role != "company_admin":
        raise HTTPException(403, "Se requiere rol de administrador de empresa")


def _require_company_member(user: User):
    if not user.company_id:
        raise HTTPException(403, "No perteneces a una empresa")


# ── Create company ────────────────────────────────────────────
@router.post("", status_code=201)
async def create_company(
    body: CompanyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Crear empresa — el usuario se convierte en company_admin."""
    if user.company_id:
        raise HTTPException(400, "Ya perteneces a una empresa")

    # Check unique NIT
    if body.nit:
        existing = await db.execute(select(Company).where(Company.nit == body.nit))
        if existing.scalar_one_or_none():
            raise HTTPException(409, "Ya existe una empresa con ese NIT")

    company = Company(
        name=body.name,
        nit=body.nit,
        industry=body.industry,
        city=body.city,
        department=body.department,
        address=body.address,
        phone=body.phone,
        email=body.email,
        website=body.website,
    )
    db.add(company)
    await db.flush()

    # Create free subscription
    max_users, max_pedidos = get_plan_limits("free")
    sub = Subscription(
        company_id=company.id,
        plan="free",
        state="active",
        max_users=max_users,
        max_pedidos_month=max_pedidos,
        started_at=datetime.now(timezone.utc),
    )
    db.add(sub)

    # Assign user as company_admin
    user.company_id = company.id
    user.company_role = "company_admin"

    await db.commit()
    await db.refresh(company)

    data = _company_to_dict(company)
    data["subscription"] = _subscription_to_dict(sub)
    return {"ok": True, "data": data}


# ── My company ────────────────────────────────────────────────
@router.get("/mine")
async def my_company(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mi empresa + suscripcion + conteo de miembros."""
    if not user.company_id:
        return {"ok": True, "data": None}

    result = await db.execute(
        select(Company)
        .options(selectinload(Company.subscription))
        .where(Company.id == user.company_id)
    )
    company = result.scalars().first()
    if not company:
        return {"ok": True, "data": None}

    member_count = (await db.execute(
        select(func.count(User.id)).where(User.company_id == company.id)
    )).scalar() or 0

    data = _company_to_dict(company)
    data["subscription"] = _subscription_to_dict(company.subscription) if company.subscription else None
    data["member_count"] = member_count
    data["my_role"] = user.company_role
    return {"ok": True, "data": data}


# ── Update company ────────────────────────────────────────────
@router.put("/{company_id}")
async def update_company(
    company_id: int,
    body: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_company_admin(user)
    if user.company_id != company_id:
        raise HTTPException(403, "No tienes acceso a esta empresa")

    company = await db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Empresa no encontrada")

    data = body.model_dump(exclude_unset=True)
    if "nit" in data and data["nit"]:
        existing = await db.execute(
            select(Company).where(Company.nit == data["nit"], Company.id != company_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(409, "Ya existe una empresa con ese NIT")

    for k, v in data.items():
        setattr(company, k, v)
    await db.commit()
    await db.refresh(company)
    return {"ok": True, "data": _company_to_dict(company)}


# ── Members ───────────────────────────────────────────────────
@router.get("/{company_id}/members")
async def list_members(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_company_member(user)
    if user.company_id != company_id:
        raise HTTPException(403, "No tienes acceso a esta empresa")

    result = await db.execute(
        select(User).where(User.company_id == company_id).order_by(User.full_name)
    )
    members = result.scalars().all()
    return {"ok": True, "data": [_member_to_dict(m) for m in members]}


@router.post("/{company_id}/members")
async def add_member(
    company_id: int,
    body: MemberAdd,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Agregar miembro por email (debe estar registrado)."""
    _require_company_admin(user)
    if user.company_id != company_id:
        raise HTTPException(403, "No tienes acceso a esta empresa")

    if body.company_role not in ("company_admin", "cotizador", "viewer"):
        raise HTTPException(400, "Rol invalido: company_admin, cotizador, viewer")

    # Check subscription limits
    company = await db.get(Company, company_id)
    if not company:
        raise HTTPException(404, "Empresa no encontrada")

    sub_result = await db.execute(
        select(Subscription).where(Subscription.company_id == company_id)
    )
    sub = sub_result.scalar_one_or_none()
    if sub:
        member_count = (await db.execute(
            select(func.count(User.id)).where(User.company_id == company_id)
        )).scalar() or 0
        if member_count >= sub.max_users:
            raise HTTPException(400, f"Limite de usuarios alcanzado ({sub.max_users}). Mejora tu plan.")

    # Find user by email
    result = await db.execute(select(User).where(User.email == body.email))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "Usuario no encontrado. Debe registrarse primero.")
    if target.company_id:
        raise HTTPException(400, "Este usuario ya pertenece a una empresa")

    target.company_id = company_id
    target.company_role = body.company_role
    await db.commit()
    return {"ok": True, "data": _member_to_dict(target)}


@router.put("/{company_id}/members/{user_id}")
async def update_member(
    company_id: int,
    user_id: int,
    body: MemberUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_company_admin(user)
    if user.company_id != company_id:
        raise HTTPException(403, "No tienes acceso a esta empresa")

    if body.company_role not in ("company_admin", "cotizador", "viewer"):
        raise HTTPException(400, "Rol invalido")

    target = await db.get(User, user_id)
    if not target or target.company_id != company_id:
        raise HTTPException(404, "Miembro no encontrado")

    target.company_role = body.company_role
    await db.commit()
    return {"ok": True, "data": _member_to_dict(target)}


@router.delete("/{company_id}/members/{user_id}")
async def remove_member(
    company_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_company_admin(user)
    if user.company_id != company_id:
        raise HTTPException(403, "No tienes acceso a esta empresa")
    if user_id == user.id:
        raise HTTPException(400, "No puedes removerte a ti mismo")

    target = await db.get(User, user_id)
    if not target or target.company_id != company_id:
        raise HTTPException(404, "Miembro no encontrado")

    target.company_id = None
    target.company_role = None
    await db.commit()
    return {"ok": True}


# ── Company pedidos ───────────────────────────────────────────
@router.get("/{company_id}/pedidos")
async def company_pedidos(
    company_id: int,
    state: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Pedidos de toda la empresa (visible a cualquier miembro)."""
    _require_company_member(user)
    if user.company_id != company_id:
        raise HTTPException(403, "No tienes acceso a esta empresa")

    query = select(Pedido).where(Pedido.company_id == company_id)
    if state:
        query = query.where(Pedido.state == state)

    total = (await db.execute(
        select(func.count()).select_from(query.subquery())
    )).scalar() or 0

    result = await db.execute(
        query.order_by(Pedido.created_at.desc()).offset(offset).limit(limit)
    )
    pedidos = result.scalars().all()

    return {
        "ok": True,
        "data": [
            {
                "id": p.id,
                "reference": p.reference,
                "title": p.title,
                "state": p.state,
                "created_by": p.created_by,
                "creator_name": p.creator.full_name if p.creator else None,
                "assigned_to": p.assigned_to,
                "region": p.region,
                "currency": p.currency,
                "item_count": p.item_count,
                "quotes_received": p.quotes_received,
                "deadline": p.deadline.isoformat() if p.deadline else None,
                "created_at": p.created_at.isoformat(),
            }
            for p in pedidos
        ],
        "total": total,
    }


@router.post("/{company_id}/pedidos/{pedido_id}/assign")
async def assign_pedido(
    company_id: int,
    pedido_id: int,
    assignee_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Asignar pedido a un cotizador de la empresa."""
    _require_company_admin(user)
    if user.company_id != company_id:
        raise HTTPException(403, "No tienes acceso a esta empresa")

    pedido = await db.get(Pedido, pedido_id)
    if not pedido or pedido.company_id != company_id:
        raise HTTPException(404, "Pedido no encontrado en esta empresa")

    assignee = await db.get(User, assignee_id)
    if not assignee or assignee.company_id != company_id:
        raise HTTPException(404, "El usuario no pertenece a esta empresa")

    pedido.assigned_to = assignee_id
    await db.commit()
    return {"ok": True, "message": f"Pedido asignado a {assignee.full_name}"}
