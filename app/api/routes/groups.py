from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.deps import require_manager
from app.models.insumo import Insumo
from app.models.insumo_group import InsumoGroup
from app.models.user import User
from app.services.matching import normalize_text

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────
class GroupCreate(BaseModel):
    name: str
    category: str | None = None
    variant_label: str | None = None
    description: str | None = None


class GroupUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    variant_label: str | None = None
    description: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class MembersAdd(BaseModel):
    insumo_ids: list[int]


class SuggestionAccept(BaseModel):
    name: str
    category: str | None = None
    variant_label: str | None = None
    insumo_ids: list[int]


# ── Helpers ────────────────────────────────────────────────────
def _group_to_dict(g: InsumoGroup, member_count: int = 0,
                   price_min: float | None = None,
                   price_max: float | None = None) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "category": g.category,
        "variant_label": g.variant_label,
        "description": g.description,
        "sort_order": g.sort_order,
        "is_active": g.is_active,
        "member_count": member_count,
        "price_range": {"min": price_min, "max": price_max},
    }


def _insumo_brief(i: Insumo) -> dict:
    return {
        "id": i.id,
        "name": i.name,
        "uom": i.uom,
        "category": i.category,
        "ref_price": i.ref_price,
        "ref_currency": i.ref_currency,
    }


# ── CRUD ───────────────────────────────────────────────────────
@router.get("")
async def list_groups(
    q: str | None = Query(None),
    category: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Listar grupos con conteo de miembros y rango de precios."""
    query = (
        select(
            InsumoGroup,
            func.count(Insumo.id).label("member_count"),
            func.min(Insumo.ref_price).label("price_min"),
            func.max(Insumo.ref_price).label("price_max"),
        )
        .outerjoin(Insumo, (Insumo.group_id == InsumoGroup.id) & (Insumo.is_active == True))
        .group_by(InsumoGroup.id)
    )

    if q:
        query = query.where(InsumoGroup.name.ilike(f"%{q}%"))
    if category:
        query = query.where(InsumoGroup.category == category)

    # Count total
    count_q = select(func.count()).select_from(
        select(InsumoGroup.id).where(InsumoGroup.is_active == True)
        .correlate(None).subquery()
    )
    if q:
        count_q = select(func.count()).select_from(
            select(InsumoGroup.id)
            .where(InsumoGroup.is_active == True, InsumoGroup.name.ilike(f"%{q}%"))
            .correlate(None).subquery()
        )
    total = (await db.execute(count_q)).scalar() or 0

    query = query.where(InsumoGroup.is_active == True)
    query = query.order_by(InsumoGroup.sort_order, InsumoGroup.name).offset(offset).limit(limit)
    rows = (await db.execute(query)).all()

    return {
        "ok": True,
        "data": [
            _group_to_dict(row[0], member_count=row[1], price_min=row[2], price_max=row[3])
            for row in rows
        ],
        "total": total,
    }


# ── Suggestions (before /{group_id} to avoid route conflict) ──
@router.get("/suggestions")
async def get_suggestions(
    category: str | None = Query(None),
    min_members: int = Query(2, ge=2),
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    from app.services.grouping import suggest_groups
    suggestions = await suggest_groups(db, category=category, min_members=min_members)
    return {"ok": True, "data": suggestions[:limit]}


@router.post("/suggestions/accept", status_code=201)
async def accept_suggestion(
    body: SuggestionAccept,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Crear grupo y asignar insumos en una sola transaccion."""
    group = InsumoGroup(
        name=body.name,
        name_normalized=normalize_text(body.name),
        category=body.category,
        variant_label=body.variant_label,
    )
    db.add(group)
    await db.flush()

    result = await db.execute(
        select(Insumo).where(Insumo.id.in_(body.insumo_ids))
    )
    count = 0
    for ins in result.scalars().all():
        ins.group_id = group.id
        count += 1

    await db.commit()
    await db.refresh(group)
    data = _group_to_dict(group, member_count=count)
    return {"ok": True, "data": data}


@router.get("/{group_id}")
async def get_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Detalle de un grupo con sus insumos miembros."""
    result = await db.execute(
        select(InsumoGroup)
        .options(selectinload(InsumoGroup.insumos))
        .where(InsumoGroup.id == group_id)
    )
    group = result.scalars().first()
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    active_insumos = [i for i in group.insumos if i.is_active]
    prices = [i.ref_price for i in active_insumos if i.ref_price is not None]

    data = _group_to_dict(
        group,
        member_count=len(active_insumos),
        price_min=min(prices) if prices else None,
        price_max=max(prices) if prices else None,
    )
    data["insumos"] = [_insumo_brief(i) for i in sorted(active_insumos, key=lambda x: x.name)]
    return {"ok": True, "data": data}


@router.post("", status_code=201)
async def create_group(
    body: GroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    group = InsumoGroup(
        name=body.name,
        name_normalized=normalize_text(body.name),
        category=body.category,
        variant_label=body.variant_label,
        description=body.description,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return {"ok": True, "data": _group_to_dict(group)}


@router.put("/{group_id}")
async def update_group(
    group_id: int,
    body: GroupUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    group = await db.get(InsumoGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        data["name_normalized"] = normalize_text(data["name"])
    for k, v in data.items():
        setattr(group, k, v)
    await db.commit()
    await db.refresh(group)
    return {"ok": True, "data": _group_to_dict(group)}


@router.delete("/{group_id}")
async def delete_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    group = await db.get(InsumoGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    group.is_active = False
    # Desasociar insumos
    result = await db.execute(
        select(Insumo).where(Insumo.group_id == group_id)
    )
    for insumo in result.scalars().all():
        insumo.group_id = None
    await db.commit()
    return {"ok": True}


# ── Members ────────────────────────────────────────────────────
@router.post("/{group_id}/members")
async def add_members(
    group_id: int,
    body: MembersAdd,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    group = await db.get(InsumoGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    result = await db.execute(
        select(Insumo).where(Insumo.id.in_(body.insumo_ids))
    )
    insumos = result.scalars().all()
    assigned = 0
    moved = 0
    for ins in insumos:
        if ins.group_id and ins.group_id != group_id:
            moved += 1
        elif ins.group_id == group_id:
            continue
        else:
            assigned += 1
        ins.group_id = group_id

    await db.commit()
    return {"ok": True, "assigned": assigned, "moved": moved}


@router.delete("/{group_id}/members/{insumo_id}")
async def remove_member(
    group_id: int,
    insumo_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    insumo = await db.get(Insumo, insumo_id)
    if not insumo or insumo.group_id != group_id:
        raise HTTPException(status_code=404, detail="Producto no encontrado en este grupo")
    insumo.group_id = None
    await db.commit()
    return {"ok": True}
