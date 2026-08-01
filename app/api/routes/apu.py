"""Analisis de precios unitarios y presupuestos de obra.

Todo el modulo es multiempresa: cada objeto se alcanza SIEMPRE bajando desde
`ApuProject.company_id`. No hay ningun endpoint que cargue una partida, linea
o computo por id sin comprobar antes a que empresa pertenece.

Roles dentro de la empresa:
    company_admin, cotizador -> pueden editar
    viewer                   -> solo lectura
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.rate_limit import PUBLIC_LIMIT, limiter
from app.core.security import get_current_user
from app.models.apu import (
    RESOURCE_TYPES, TEMPLATE_LINE_TYPES,
    ApuComputo, ApuItem, ApuItemSummary, ApuLine, ApuProject, ApuRubro,
    ApuTemplate, ApuTemplateLine,
)
from app.models.insumo import Insumo
from app.models.user import User
from app.services import quota
from app.services.apu_engine import (
    FormulaError, TemplateLineSpec, apu_round, compute_computo_subtotal,
    compute_item, compute_line_subtotal, detect_cycles,
    order_items_for_computation,
)

router = APIRouter()

EDITOR_ROLES = ("company_admin", "cotizador")
# Roles globales del staff que pueden auditar cualquier empresa.
STAFF_OVERRIDE = ("admin", "superadmin")


# ── Schemas ────────────────────────────────────────────────────
class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=50)
    client_name: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    region: str | None = Field(default=None, max_length=100)
    currency: str = Field(default="BOB", max_length=10)
    template_id: int | None = None
    notes: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=50)
    client_name: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    region: str | None = Field(default=None, max_length=100)
    template_id: int | None = None
    state: str | None = None
    notes: str | None = None


class RubroIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=30)
    sequence: int = 10


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    uom: str = Field(default="m2", max_length=30)
    code: str | None = Field(default=None, max_length=30)
    rubro_id: int | None = None
    quantity: float = 1.0
    sequence: int = 10
    is_complementary: bool = False
    reference_price: float | None = None
    notes: str | None = None


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    uom: str | None = Field(default=None, max_length=30)
    code: str | None = Field(default=None, max_length=30)
    rubro_id: int | None = None
    quantity: float | None = None
    quantity_from_computo: bool | None = None
    sequence: int | None = None
    is_complementary: bool | None = None
    reference_price: float | None = None
    notes: str | None = None


class LineIn(BaseModel):
    type: str
    name: str | None = Field(default=None, max_length=500)
    uom: str | None = Field(default=None, max_length=30)
    quantity: float = 1.0
    price_unit: float | None = None
    insumo_id: int | None = None
    linked_item_id: int | None = None
    sequence: int = 10
    notes: str | None = Field(default=None, max_length=500)


class LineUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=500)
    uom: str | None = Field(default=None, max_length=30)
    quantity: float | None = None
    price_unit: float | None = None
    sequence: int | None = None
    notes: str | None = Field(default=None, max_length=500)


class ComputoIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    pieces: float = 1.0
    length: float = 1.0
    width: float = 1.0
    height: float = 1.0
    sequence: int = 10


class ComputoUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    pieces: float | None = None
    length: float | None = None
    width: float | None = None
    height: float | None = None
    sequence: int | None = None


# ── Autorizacion ───────────────────────────────────────────────
def _require_company(user: User) -> int:
    if not user.company_id:
        raise HTTPException(
            status_code=403,
            detail="Necesitas pertenecer a una empresa para usar presupuestos",
        )
    return user.company_id


def _require_editor(user: User) -> None:
    """viewer es solo lectura; el staff global puede editar para soporte."""
    if user.role in STAFF_OVERRIDE:
        return
    if user.company_role not in EDITOR_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Tu rol en la empresa es de solo lectura",
        )


async def _get_project(
    db: AsyncSession, project_id: int, user: User, *, for_edit: bool = False,
) -> ApuProject:
    project = await db.get(ApuProject, project_id)
    if project is None or not project.is_active:
        raise HTTPException(404, "Proyecto no encontrado")
    if user.role not in STAFF_OVERRIDE and project.company_id != user.company_id:
        # 404 y no 403: no confirmamos la existencia de datos de otra empresa.
        raise HTTPException(404, "Proyecto no encontrado")
    if for_edit:
        _require_editor(user)
    return project


async def _get_item(
    db: AsyncSession, item_id: int, user: User, *, for_edit: bool = False,
) -> ApuItem:
    item = await db.get(ApuItem, item_id)
    if item is None:
        raise HTTPException(404, "Partida no encontrada")
    await _get_project(db, item.project_id, user, for_edit=for_edit)
    return item


async def _get_line(db: AsyncSession, line_id: int, user: User) -> ApuLine:
    line = await db.get(ApuLine, line_id)
    if line is None:
        raise HTTPException(404, "Recurso no encontrado")
    await _get_item(db, line.item_id, user, for_edit=True)
    return line


async def _get_computo(db: AsyncSession, computo_id: int, user: User) -> ApuComputo:
    computo = await db.get(ApuComputo, computo_id)
    if computo is None:
        raise HTTPException(404, "Computo no encontrado")
    await _get_item(db, computo.item_id, user, for_edit=True)
    return computo


# ── Serializacion ──────────────────────────────────────────────
def _project_dict(p: ApuProject, item_count: int = 0) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "code": p.code,
        "client_name": p.client_name,
        "location": p.location,
        "region": p.region,
        "currency": p.currency,
        "state": p.state,
        "template_id": p.template_id,
        "total_budget": p.total_budget,
        "item_count": item_count,
        "notes": p.notes,
        "last_computed_at": p.last_computed_at.isoformat() if p.last_computed_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _item_dict(i: ApuItem) -> dict:
    return {
        "id": i.id,
        "code": i.code,
        "name": i.name,
        "uom": i.uom,
        "rubro_id": i.rubro_id,
        "sequence": i.sequence,
        "quantity": i.quantity,
        "quantity_from_computo": i.quantity_from_computo,
        "is_complementary": i.is_complementary,
        "reference_price": i.reference_price,
        "mat_cost": i.mat_cost,
        "mo_cost": i.mo_cost,
        "eq_cost": i.eq_cost,
        "direct_cost": i.direct_cost,
        "unit_price": i.unit_price,
        "total_price": i.total_price,
        "notes": i.notes,
    }


def _line_dict(l: ApuLine) -> dict:
    return {
        "id": l.id,
        "type": l.type,
        "name": l.name,
        "uom": l.uom,
        "quantity": l.quantity,
        "price_unit": l.price_unit,
        "price_subtotal": l.price_subtotal,
        "insumo_id": l.insumo_id,
        "linked_item_id": l.linked_item_id,
        "sequence": l.sequence,
        "price_source": l.price_source,
        "price_updated_at": l.price_updated_at.isoformat() if l.price_updated_at else None,
        "notes": l.notes,
    }


def _computo_dict(c: ApuComputo) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "pieces": c.pieces,
        "length": c.length,
        "width": c.width,
        "height": c.height,
        "subtotal": c.subtotal,
        "sequence": c.sequence,
    }


def _summary_dict(s: ApuItemSummary) -> dict:
    return {
        "code": s.code,
        "name": s.name,
        "line_type": s.line_type,
        "value_formula": s.value_formula,
        "amount": s.amount,
        "is_total": s.is_total,
        "sequence": s.sequence,
    }


# ── Motor: recalculo persistente ───────────────────────────────
async def _load_template_specs(
    db: AsyncSession, template_id: int | None,
) -> list[TemplateLineSpec]:
    if not template_id:
        return []
    rows = (await db.execute(
        select(ApuTemplateLine)
        .where(ApuTemplateLine.template_id == template_id)
        .order_by(ApuTemplateLine.sequence, ApuTemplateLine.id)
    )).scalars().all()
    return [
        TemplateLineSpec(
            code=r.code, name=r.name, type=r.type, value=r.value,
            formula=r.formula, is_total=r.is_total, sequence=r.sequence,
        )
        for r in rows
    ]


async def recompute_project(db: AsyncSession, project: ApuProject) -> dict:
    """Recalcula todas las partidas y el total, y materializa las planillas.

    Las partidas complementarias se calculan primero para que las lineas
    'sub' que las consumen tengan sus costos disponibles.
    """
    items = (await db.execute(
        select(ApuItem)
        .where(ApuItem.project_id == project.id)
        .options(selectinload(ApuItem.lines), selectinload(ApuItem.computos))
    )).scalars().unique().all()

    template_specs = await _load_template_specs(db, project.template_id)
    cycles = detect_cycles(items)
    ordered = order_items_for_computation(items)

    sub_costs: dict[int, tuple[float, float, float]] = {}
    total_budget = 0.0

    for item in ordered:
        # La cantidad sale de los computos metricos salvo que se fije a mano.
        if item.quantity_from_computo and item.computos:
            qty = 0.0
            for c in item.computos:
                c.subtotal = compute_computo_subtotal(
                    c.pieces, c.length, c.width, c.height, project.decimals_qty,
                )
                qty += c.subtotal
            item.quantity = apu_round(qty, project.decimals_qty)

        for line in item.lines:
            line.price_subtotal = compute_line_subtotal(
                line.quantity, line.price_unit, project.decimals_subtotal,
            )

        try:
            result = compute_item(
                item.lines,
                template_specs,
                quantity=item.quantity,
                reference_price=item.reference_price,
                decimals_subtotal=project.decimals_subtotal,
                decimals_total=project.decimals_total,
                sub_costs=sub_costs,
            )
        except FormulaError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Error en la plantilla de calculo: {exc}",
            )

        item.mat_cost = result.mat_cost
        item.mo_cost = result.mo_cost
        item.eq_cost = result.eq_cost
        item.direct_cost = result.direct_cost
        item.unit_price = result.unit_price
        item.total_price = result.total_price
        sub_costs[item.id] = (result.mat_cost, result.mo_cost, result.eq_cost)

        # Reemplazar la planilla materializada
        await db.execute(
            ApuItemSummary.__table__.delete().where(
                ApuItemSummary.__table__.c.item_id == item.id
            )
        )
        for row in result.summary:
            db.add(ApuItemSummary(
                item_id=item.id, sequence=row.sequence, code=row.code,
                name=row.name, line_type=row.line_type,
                value_formula=row.value_formula, amount=row.amount,
                is_total=row.is_total,
            ))

        # Las complementarias son insumos de otras partidas: no suman al total.
        if not item.is_complementary:
            total_budget += result.total_price

    project.total_budget = apu_round(total_budget, project.decimals_total)
    project.last_computed_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "total_budget": project.total_budget,
        "items_computed": len(ordered),
        "cycles": cycles,
    }


# ── Proyectos ──────────────────────────────────────────────────
@router.get("/projects")
async def list_projects(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_id = _require_company(user)
    base = select(ApuProject).where(
        ApuProject.company_id == company_id, ApuProject.is_active == True,  # noqa: E712
    )
    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar() or 0
    rows = (await db.execute(
        base.order_by(ApuProject.created_at.desc()).offset(offset).limit(limit)
    )).scalars().all()

    counts = dict((await db.execute(
        select(ApuItem.project_id, func.count(ApuItem.id))
        .where(ApuItem.project_id.in_([r.id for r in rows] or [0]))
        .group_by(ApuItem.project_id)
    )).all())

    return {
        "ok": True,
        "data": [_project_dict(p, counts.get(p.id, 0)) for p in rows],
        "total": total,
    }


@router.post("/projects", status_code=201)
async def create_project(
    body: ProjectIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_id = _require_company(user)
    _require_editor(user)
    # Cuota del plan: devuelve 402 con el motivo si se alcanzo el limite.
    await quota.assert_can_create_project(db, company_id)

    template_id = body.template_id
    if template_id is not None:
        await _get_template_for_company(db, template_id, company_id)
    else:
        template_id = await _default_template_id(db, company_id)

    project = ApuProject(
        company_id=company_id,
        created_by=user.id,
        name=body.name,
        code=body.code,
        client_name=body.client_name,
        location=body.location,
        region=body.region,
        currency=body.currency,
        template_id=template_id,
        notes=body.notes,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return {"ok": True, "data": _project_dict(project)}


@router.get("/projects/{project_id}")
async def get_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await _get_project(db, project_id, user)

    rubros = (await db.execute(
        select(ApuRubro).where(ApuRubro.project_id == project.id)
        .order_by(ApuRubro.sequence, ApuRubro.id)
    )).scalars().all()
    items = (await db.execute(
        select(ApuItem).where(ApuItem.project_id == project.id)
        .order_by(ApuItem.sequence, ApuItem.id)
    )).scalars().all()

    by_rubro: dict[int | None, list] = {}
    for it in items:
        by_rubro.setdefault(it.rubro_id, []).append(it)

    def _rubro_payload(r: ApuRubro) -> dict:
        own = by_rubro.get(r.id, [])
        return {
            "id": r.id,
            "name": r.name,
            "code": r.code,
            "sequence": r.sequence,
            "total": apu_round(
                sum(i.total_price for i in own if not i.is_complementary),
                project.decimals_total,
            ),
            "items": [_item_dict(i) for i in own],
        }

    data = _project_dict(project, len(items))
    data["rubros"] = [_rubro_payload(r) for r in rubros]
    data["unassigned_items"] = [_item_dict(i) for i in by_rubro.get(None, [])]
    return {"ok": True, "data": data}


@router.put("/projects/{project_id}")
async def update_project(
    project_id: int,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await _get_project(db, project_id, user, for_edit=True)
    data = body.model_dump(exclude_unset=True)

    if "state" in data and data["state"] not in ("draft", "active", "closed"):
        raise HTTPException(400, "Estado invalido")
    if data.get("template_id") is not None:
        await _get_template_for_company(db, data["template_id"], project.company_id)

    for field, value in data.items():
        setattr(project, field, value)
    await db.commit()
    return {"ok": True, "data": _project_dict(project)}


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Baja logica: libera el cupo del plan sin destruir el historico."""
    project = await _get_project(db, project_id, user, for_edit=True)
    project.is_active = False
    await db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/recompute")
async def recompute(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await _get_project(db, project_id, user, for_edit=True)
    return {"ok": True, "data": await recompute_project(db, project)}


@router.post("/projects/{project_id}/refresh-prices")
async def refresh_prices(
    project_id: int,
    include_manual: bool = Query(
        False,
        description="Tambien pisar los precios escritos a mano (negociados)",
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Trae el precio vigente de mercado para los recursos del catalogo.

    Es explicito a proposito: un presupuesto no debe moverse solo. Si el
    proyecto tiene region, se prefiere el precio regional.

    Los precios escritos a mano se RESPETAN por defecto: suelen ser precios
    negociados con un proveedor y pisarlos en silencio destruye trabajo del
    usuario. Se pueden forzar con include_manual=true.
    """
    from app.models.insumo import InsumoRegionalPrice

    project = await _get_project(db, project_id, user, for_edit=True)

    query = (
        select(ApuLine)
        .join(ApuItem, ApuLine.item_id == ApuItem.id)
        .where(ApuItem.project_id == project.id, ApuLine.insumo_id.is_not(None))
    )
    if not include_manual:
        query = query.where(ApuLine.price_source != "manual")

    async def _count_manual() -> int:
        """Cuantos recursos se dejaron intactos por tener precio negociado."""
        if include_manual:
            return 0
        return (await db.execute(
            select(func.count(ApuLine.id))
            .join(ApuItem, ApuLine.item_id == ApuItem.id)
            .where(
                ApuItem.project_id == project.id,
                ApuLine.insumo_id.is_not(None),
                ApuLine.price_source == "manual",
            )
        )).scalar() or 0

    lines = (await db.execute(query)).scalars().all()
    if not lines:
        # Puede no haber nada que refrescar y aun asi haber precios manuales
        # conservados: hay que informarlo para que la UI lo explique.
        return {
            "ok": True,
            "data": {
                "updated": 0, "unchanged": 0, "not_found": 0,
                "kept_manual": await _count_manual(),
            },
        }

    insumo_ids = {l.insumo_id for l in lines}
    insumos = {
        i.id: i for i in (await db.execute(
            select(Insumo).where(Insumo.id.in_(insumo_ids))
        )).scalars().all()
    }

    regional: dict[int, float] = {}
    if project.region:
        rows = (await db.execute(
            select(InsumoRegionalPrice).where(
                InsumoRegionalPrice.insumo_id.in_(insumo_ids),
                InsumoRegionalPrice.region == project.region,
                InsumoRegionalPrice.currency == project.currency,
            )
        )).scalars().all()
        regional = {r.insumo_id: r.price for r in rows}

    now = datetime.now(timezone.utc)
    updated = unchanged = not_found = 0
    for line in lines:
        insumo = insumos.get(line.insumo_id)
        if insumo is None:
            not_found += 1
            continue
        new_price = regional.get(insumo.id)
        source = "regional"
        if new_price is None:
            new_price = insumo.ref_price
            source = "market"
        if new_price is None:
            not_found += 1
            continue
        new_price = apu_round(new_price, project.decimals_price)
        if new_price == apu_round(line.price_unit, project.decimals_price):
            unchanged += 1
            continue
        line.price_unit = new_price
        line.price_source = source
        line.price_updated_at = now
        updated += 1

    kept_manual = await _count_manual()

    await db.commit()
    await db.refresh(project)
    result = await recompute_project(db, project)
    return {
        "ok": True,
        "data": {
            "updated": updated, "unchanged": unchanged, "not_found": not_found,
            "kept_manual": kept_manual,
            "total_budget": result["total_budget"],
        },
    }


# ── Rubros ─────────────────────────────────────────────────────
@router.post("/projects/{project_id}/rubros", status_code=201)
async def create_rubro(
    project_id: int,
    body: RubroIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await _get_project(db, project_id, user, for_edit=True)
    rubro = ApuRubro(project_id=project.id, **body.model_dump())
    db.add(rubro)
    await db.commit()
    await db.refresh(rubro)
    return {
        "ok": True,
        "data": {"id": rubro.id, "name": rubro.name, "code": rubro.code,
                 "sequence": rubro.sequence},
    }


@router.delete("/rubros/{rubro_id}")
async def delete_rubro(
    rubro_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rubro = await db.get(ApuRubro, rubro_id)
    if rubro is None:
        raise HTTPException(404, "Rubro no encontrado")
    await _get_project(db, rubro.project_id, user, for_edit=True)
    await db.delete(rubro)  # las partidas quedan sin rubro (SET NULL)
    await db.commit()
    return {"ok": True}


# ── Partidas ───────────────────────────────────────────────────
@router.post("/projects/{project_id}/items", status_code=201)
async def create_item(
    project_id: int,
    body: ItemIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await _get_project(db, project_id, user, for_edit=True)
    data = body.model_dump()

    if data.get("rubro_id") is not None:
        rubro = await db.get(ApuRubro, data["rubro_id"])
        if rubro is None or rubro.project_id != project.id:
            raise HTTPException(400, "El rubro no pertenece a este proyecto")

    item = ApuItem(project_id=project.id, **data)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"ok": True, "data": _item_dict(item)}


@router.get("/items/{item_id}")
async def get_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = await _get_item(db, item_id, user)
    lines = (await db.execute(
        select(ApuLine).where(ApuLine.item_id == item.id)
        .order_by(ApuLine.sequence, ApuLine.id)
    )).scalars().all()
    computos = (await db.execute(
        select(ApuComputo).where(ApuComputo.item_id == item.id)
        .order_by(ApuComputo.sequence, ApuComputo.id)
    )).scalars().all()
    summary = (await db.execute(
        select(ApuItemSummary).where(ApuItemSummary.item_id == item.id)
        .order_by(ApuItemSummary.sequence, ApuItemSummary.id)
    )).scalars().all()

    data = _item_dict(item)
    data["lines"] = [_line_dict(l) for l in lines]
    data["computos"] = [_computo_dict(c) for c in computos]
    data["summary"] = [_summary_dict(s) for s in summary]
    return {"ok": True, "data": data}


@router.put("/items/{item_id}")
async def update_item(
    item_id: int,
    body: ItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = await _get_item(db, item_id, user, for_edit=True)
    data = body.model_dump(exclude_unset=True)

    if data.get("rubro_id") is not None:
        rubro = await db.get(ApuRubro, data["rubro_id"])
        if rubro is None or rubro.project_id != item.project_id:
            raise HTTPException(400, "El rubro no pertenece a este proyecto")
    # Fijar la cantidad a mano desactiva el calculo desde computos.
    if "quantity" in data and "quantity_from_computo" not in data:
        data["quantity_from_computo"] = False

    for field, value in data.items():
        setattr(item, field, value)
    await db.commit()
    return {"ok": True, "data": _item_dict(item)}


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = await _get_item(db, item_id, user, for_edit=True)
    await db.delete(item)
    await db.commit()
    return {"ok": True}


# ── Recursos de la partida ─────────────────────────────────────
@router.post("/items/{item_id}/lines", status_code=201)
async def add_line(
    item_id: int,
    body: LineIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = await _get_item(db, item_id, user, for_edit=True)

    if body.type not in RESOURCE_TYPES:
        raise HTTPException(400, f"Tipo invalido. Use uno de: {', '.join(RESOURCE_TYPES)}")

    name, uom, price = body.name, body.uom, body.price_unit
    source = "manual"

    if body.insumo_id is not None:
        insumo = await db.get(Insumo, body.insumo_id)
        if insumo is None or not insumo.is_active:
            raise HTTPException(400, "El insumo no existe")
        # Copia del catalogo: el presupuesto no debe moverse despues solo.
        name = name or insumo.name
        uom = uom or insumo.uom
        if price is None:
            price = insumo.ref_price or 0.0
            source = "market"

    if body.linked_item_id is not None:
        linked = await db.get(ApuItem, body.linked_item_id)
        if linked is None or linked.project_id != item.project_id:
            raise HTTPException(400, "La partida enlazada no pertenece a este proyecto")
        if linked.id == item.id:
            raise HTTPException(400, "Una partida no puede consumirse a si misma")
        name = name or linked.name
        uom = uom or linked.uom

    if not name:
        raise HTTPException(400, "Falta la descripcion del recurso")

    line = ApuLine(
        item_id=item.id,
        type=body.type,
        insumo_id=body.insumo_id,
        linked_item_id=body.linked_item_id,
        name=name,
        uom=uom or "u",
        quantity=body.quantity,
        price_unit=price or 0.0,
        sequence=body.sequence,
        notes=body.notes,
        price_source=source,
        price_updated_at=datetime.now(timezone.utc) if source != "manual" else None,
    )
    line.price_subtotal = compute_line_subtotal(line.quantity, line.price_unit)
    db.add(line)
    await db.commit()
    await db.refresh(line)
    return {"ok": True, "data": _line_dict(line)}


@router.put("/lines/{line_id}")
async def update_line(
    line_id: int,
    body: LineUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    line = await _get_line(db, line_id, user)
    data = body.model_dump(exclude_unset=True)
    if "price_unit" in data:
        line.price_source = "manual"
        line.price_updated_at = datetime.now(timezone.utc)
    for field, value in data.items():
        setattr(line, field, value)
    line.price_subtotal = compute_line_subtotal(line.quantity, line.price_unit)
    await db.commit()
    return {"ok": True, "data": _line_dict(line)}


@router.delete("/lines/{line_id}")
async def delete_line(
    line_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    line = await _get_line(db, line_id, user)
    await db.delete(line)
    await db.commit()
    return {"ok": True}


# ── Computos metricos ──────────────────────────────────────────
@router.post("/items/{item_id}/computos", status_code=201)
async def add_computo(
    item_id: int,
    body: ComputoIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = await _get_item(db, item_id, user, for_edit=True)
    computo = ApuComputo(item_id=item.id, **body.model_dump())
    computo.subtotal = compute_computo_subtotal(
        computo.pieces, computo.length, computo.width, computo.height,
    )
    db.add(computo)
    await db.commit()
    await db.refresh(computo)
    return {"ok": True, "data": _computo_dict(computo)}


@router.put("/computos/{computo_id}")
async def update_computo(
    computo_id: int,
    body: ComputoUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    computo = await _get_computo(db, computo_id, user)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(computo, field, value)
    computo.subtotal = compute_computo_subtotal(
        computo.pieces, computo.length, computo.width, computo.height,
    )
    await db.commit()
    return {"ok": True, "data": _computo_dict(computo)}


@router.delete("/computos/{computo_id}")
async def delete_computo(
    computo_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    computo = await _get_computo(db, computo_id, user)
    await db.delete(computo)
    await db.commit()
    return {"ok": True}


# ── Plantillas de calculo ──────────────────────────────────────
async def _get_template_for_company(
    db: AsyncSession, template_id: int, company_id: int,
) -> ApuTemplate:
    template = await db.get(ApuTemplate, template_id)
    if template is None or not template.is_active:
        raise HTTPException(404, "Plantilla no encontrada")
    # Solo las globales o las de la propia empresa.
    if template.company_id is not None and template.company_id != company_id:
        raise HTTPException(404, "Plantilla no encontrada")
    return template


async def _default_template_id(db: AsyncSession, company_id: int) -> int | None:
    row = (await db.execute(
        select(ApuTemplate.id).where(
            ApuTemplate.is_active == True,  # noqa: E712
            ApuTemplate.company_id.is_(None),
        ).order_by(ApuTemplate.id).limit(1)
    )).scalar_one_or_none()
    return row


@router.get("/templates")
async def list_templates(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_id = _require_company(user)
    rows = (await db.execute(
        select(ApuTemplate).where(
            ApuTemplate.is_active == True,  # noqa: E712
            (ApuTemplate.company_id.is_(None)) | (ApuTemplate.company_id == company_id),
        ).options(selectinload(ApuTemplate.lines)).order_by(ApuTemplate.id)
    )).scalars().unique().all()

    return {
        "ok": True,
        "data": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "is_global": t.company_id is None,
                "lines": [
                    {
                        "code": l.code, "name": l.name, "type": l.type,
                        "value": l.value, "formula": l.formula,
                        "is_total": l.is_total, "sequence": l.sequence,
                    }
                    for l in t.lines
                ],
            }
            for t in rows
        ],
    }


# ── Resumen de recursos del proyecto ───────────────────────────
@router.get("/projects/{project_id}/resources")
async def project_resources(
    project_id: int,
    type: str | None = Query(None, description="Filtrar por mat, mo, eq"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Insumos consolidados de toda la obra, con cantidad total y costo.

    Es el requerimiento de materiales/mano de obra/equipo: la cantidad real
    de cada recurso es su rendimiento multiplicado por la cantidad de la
    partida que lo consume, sumado en todas las partidas.

    Las partidas complementarias se excluyen: su costo ya viaja dentro de la
    partida que las consume, y contarlas dos veces inflaria el requerimiento.
    """
    project = await _get_project(db, project_id, user)

    if type is not None and type not in RESOURCE_TYPES:
        raise HTTPException(400, f"Tipo invalido. Use uno de: {', '.join(RESOURCE_TYPES)}")

    rows = (await db.execute(
        select(ApuLine, ApuItem.quantity, ApuItem.is_complementary)
        .join(ApuItem, ApuLine.item_id == ApuItem.id)
        .where(ApuItem.project_id == project.id)
    )).all()

    agregado: dict[tuple, dict] = {}
    for line, item_qty, is_complementary in rows:
        if is_complementary or line.type == "sub":
            continue
        if type is not None and line.type != type:
            continue
        # Agrupar por recurso del catalogo cuando exista; si no, por nombre.
        clave = (line.type, line.insumo_id or f"txt:{line.name.strip().lower()}", line.uom)
        entrada = agregado.setdefault(clave, {
            "type": line.type,
            "insumo_id": line.insumo_id,
            "name": line.name,
            "uom": line.uom,
            "quantity": 0.0,
            "amount": 0.0,
            "price_unit": line.price_unit,
            "used_in_items": 0,
        })
        cantidad = (line.quantity or 0.0) * (item_qty or 0.0)
        entrada["quantity"] += cantidad
        entrada["amount"] += cantidad * (line.price_unit or 0.0)
        entrada["used_in_items"] += 1

    data = []
    for entrada in agregado.values():
        entrada["quantity"] = apu_round(entrada["quantity"], project.decimals_qty)
        entrada["amount"] = apu_round(entrada["amount"], project.decimals_total)
        data.append(entrada)
    data.sort(key=lambda e: (e["type"], -e["amount"]))

    totales = {t: 0.0 for t in ("mat", "mo", "eq")}
    for e in data:
        if e["type"] in totales:
            totales[e["type"]] += e["amount"]

    return {
        "ok": True,
        "data": data,
        "totals": {k: apu_round(v, project.decimals_total) for k, v in totales.items()},
        "currency": project.currency,
    }


# ── Exportacion al formato canonico de Odoo ────────────────────
@router.get("/projects/{project_id}/export.xlsx")
async def export_project_xlsx(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Descarga el presupuesto como libro Excel que Odoo importa tal cual.

    Es la via de migracion al ERP que no requiere escribir codigo en Odoo:
    el asistente `apu.import.wizard` de ssa_construction_apu lee este formato.
    """
    from fastapi.responses import Response
    from app.services.apu_export import build_workbook, default_filename

    project = await _get_project(db, project_id, user)

    # Cargar el arbol completo; build_workbook no consulta la base.
    project = (await db.execute(
        select(ApuProject)
        .where(ApuProject.id == project.id)
        .options(
            selectinload(ApuProject.rubros),
            selectinload(ApuProject.items).selectinload(ApuItem.lines),
            selectinload(ApuProject.items).selectinload(ApuItem.computos),
            selectinload(ApuProject.template).selectinload(ApuTemplate.lines),
        )
    )).scalars().unique().one()

    content = build_workbook(project, project.template)
    filename = default_filename(project)
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            # filename entre comillas: el nombre del proyecto lo pone el usuario.
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


# ── Estado del plan (para la UI) ───────────────────────────────
@router.get("/quota")
async def get_quota(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_id = _require_company(user)
    return {"ok": True, "data": await quota.describe(db, company_id)}
