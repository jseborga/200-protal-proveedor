"""Biblioteca de insumos propia de cada empresa + cola de curacion.

Dos audiencias distintas en un mismo archivo:

* `/api/v1/company-insumos/*` — la empresa gestiona SUS insumos. Aislado por
  company_id, con los mismos roles que el modulo de presupuestos.
* `/api/v1/company-insumos/suggestions/*` — el staff del portal revisa lo que
  las empresas aportan al catalogo publico.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_staff
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.company_insumo import (
    SUGGESTION_STATES, CompanyInsumo, PriceSuggestion,
)
from app.models.insumo import Insumo
from app.models.user import User
from app.services import price_curation, price_suggestions

router = APIRouter()

EDITOR_ROLES = ("company_admin", "cotizador")
STAFF_OVERRIDE = ("admin", "superadmin")
RESOURCE_TYPES = ("mat", "mo", "eq", "sub")


# ── Schemas ────────────────────────────────────────────────────
class CompanyInsumoIn(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    type: str = "mat"
    uom: str = Field(default="u", max_length=30)
    code: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=100)
    description: str | None = None
    reference_price: float = Field(default=0.0, ge=0)
    currency: str = Field(default="BOB", max_length=10)
    source_insumo_id: int | None = None


class CompanyInsumoUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    type: str | None = None
    uom: str | None = Field(default=None, max_length=30)
    code: str | None = Field(default=None, max_length=50)
    category: str | None = Field(default=None, max_length=100)
    description: str | None = None
    reference_price: float | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ReviewIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class CurationConfigIn(BaseModel):
    min_samples: int | None = Field(default=None, ge=1, le=100)
    z_auto: float | None = Field(default=None, ge=0, le=10)
    pct_auto: float | None = Field(default=None, ge=0, le=100)
    max_ratio: float | None = Field(default=None, ge=2, le=1000)
    window_days: int | None = Field(default=None, ge=30, le=3650)
    auto_accept_enabled: bool | None = None


# ── Autorizacion ───────────────────────────────────────────────
def _require_company(user: User) -> int:
    if not user.company_id:
        raise HTTPException(403, "Necesitas pertenecer a una empresa")
    return user.company_id


def _require_editor(user: User) -> None:
    if user.role in STAFF_OVERRIDE:
        return
    if user.company_role not in EDITOR_ROLES:
        raise HTTPException(403, "Tu rol en la empresa es de solo lectura")


async def _get_own(db: AsyncSession, insumo_id: int, user: User) -> CompanyInsumo:
    """Carga un insumo de empresa comprobando SIEMPRE la pertenencia."""
    row = await db.get(CompanyInsumo, insumo_id)
    if row is None or not row.is_active:
        raise HTTPException(404, "Insumo no encontrado")
    if user.role not in STAFF_OVERRIDE and row.company_id != user.company_id:
        raise HTTPException(404, "Insumo no encontrado")
    return row


def _dict(ci: CompanyInsumo) -> dict:
    return {
        "id": ci.id,
        "name": ci.name,
        "code": ci.code,
        "type": ci.type,
        "uom": ci.uom,
        "category": ci.category,
        "description": ci.description,
        "reference_price": ci.reference_price,
        "currency": ci.currency,
        "source_type": ci.source_type,
        "source_insumo_id": ci.source_insumo_id,
        "proposed_to_catalog": ci.proposed_to_catalog,
        "last_price_update": (
            ci.last_price_update.isoformat() if ci.last_price_update else None
        ),
    }


# ── Biblioteca de la empresa ───────────────────────────────────
@router.get("")
async def list_company_insumos(
    q: str | None = Query(None, max_length=100),
    type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company_id = _require_company(user)
    base = select(CompanyInsumo).where(
        CompanyInsumo.company_id == company_id,
        CompanyInsumo.is_active == True,  # noqa: E712
    )
    if type:
        if type not in RESOURCE_TYPES:
            raise HTTPException(400, "Tipo invalido")
        base = base.where(CompanyInsumo.type == type)
    if q:
        patron = f"%{q.strip().lower()}%"
        base = base.where(or_(
            func.lower(CompanyInsumo.name).like(patron),
            func.lower(CompanyInsumo.code).like(patron),
        ))

    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar() or 0
    rows = (await db.execute(
        base.order_by(CompanyInsumo.name).offset(offset).limit(limit)
    )).scalars().all()
    return {"ok": True, "data": [_dict(r) for r in rows], "total": total}


@router.post("", status_code=201)
async def create_company_insumo(
    body: CompanyInsumoIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services.matching import normalize_text

    company_id = _require_company(user)
    _require_editor(user)

    if body.type not in RESOURCE_TYPES:
        raise HTTPException(400, "Tipo invalido")

    source_type = "manual"
    if body.source_insumo_id is not None:
        insumo = await db.get(Insumo, body.source_insumo_id)
        if insumo is None or not insumo.is_active:
            raise HTTPException(400, "El insumo del catalogo no existe")
        source_type = "catalog"

    if body.code:
        existe = (await db.execute(
            select(func.count(CompanyInsumo.id)).where(
                CompanyInsumo.company_id == company_id,
                CompanyInsumo.code == body.code,
            )
        )).scalar() or 0
        if existe:
            raise HTTPException(409, "Ya tenes un insumo con ese codigo")

    ci = CompanyInsumo(
        company_id=company_id,
        name=body.name,
        name_normalized=normalize_text(body.name),
        code=body.code,
        type=body.type,
        uom=body.uom,
        category=body.category,
        description=body.description,
        reference_price=body.reference_price,
        currency=body.currency,
        source_type=source_type,
        source_insumo_id=body.source_insumo_id,
        last_price_update=datetime.now(timezone.utc),
    )
    db.add(ci)
    await db.commit()
    await db.refresh(ci)
    return {"ok": True, "data": _dict(ci)}


@router.put("/{insumo_id}")
async def update_company_insumo(
    insumo_id: int,
    body: CompanyInsumoUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services.matching import normalize_text

    ci = await _get_own(db, insumo_id, user)
    _require_editor(user)

    data = body.model_dump(exclude_unset=True)
    if data.get("type") and data["type"] not in RESOURCE_TYPES:
        raise HTTPException(400, "Tipo invalido")

    precio_cambio = (
        "reference_price" in data and data["reference_price"] != ci.reference_price
    )
    for field, value in data.items():
        setattr(ci, field, value)
    if "name" in data:
        ci.name_normalized = normalize_text(data["name"])
    if precio_cambio:
        ci.last_price_update = datetime.now(timezone.utc)

    # Si esta vinculado al catalogo y la empresa corrigio el precio, ese dato
    # es un aporte: alguien cotizo de verdad.
    if precio_cambio and ci.source_type == "catalog" and ci.source_insumo_id:
        await price_suggestions.suggest_price_update(
            db,
            insumo_id=ci.source_insumo_id,
            suggested_price=ci.reference_price,
            company_id=ci.company_id,
            user_id=user.id,
            source="manual",
            source_ref=f"company_insumo:{ci.id}",
            currency=ci.currency,
        )

    await db.commit()
    return {"ok": True, "data": _dict(ci)}


@router.delete("/{insumo_id}")
async def delete_company_insumo(
    insumo_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ci = await _get_own(db, insumo_id, user)
    _require_editor(user)
    ci.is_active = False
    await db.commit()
    return {"ok": True}


@router.post("/{insumo_id}/import-from-catalog", status_code=201)
async def import_from_catalog(
    insumo_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Copia un insumo del catalogo publico a la biblioteca de la empresa."""
    from app.services.matching import normalize_text

    company_id = _require_company(user)
    _require_editor(user)

    insumo = await db.get(Insumo, insumo_id)
    if insumo is None or not insumo.is_active:
        raise HTTPException(404, "Insumo del catalogo no encontrado")

    ya = (await db.execute(
        select(CompanyInsumo).where(
            CompanyInsumo.company_id == company_id,
            CompanyInsumo.source_insumo_id == insumo.id,
            CompanyInsumo.is_active == True,  # noqa: E712
        )
    )).scalar_one_or_none()
    if ya is not None:
        return {"ok": True, "data": _dict(ya), "already_existed": True}

    ci = CompanyInsumo(
        company_id=company_id,
        name=insumo.name,
        name_normalized=normalize_text(insumo.name),
        code=insumo.code,
        type="mat",
        uom=insumo.uom,
        category=insumo.category,
        reference_price=insumo.ref_price or 0.0,
        currency=insumo.ref_currency or "BOB",
        source_type="catalog",
        source_insumo_id=insumo.id,
        last_price_update=datetime.now(timezone.utc),
    )
    db.add(ci)
    await db.commit()
    await db.refresh(ci)
    return {"ok": True, "data": _dict(ci), "already_existed": False}


@router.post("/{insumo_id}/propose-to-catalog")
async def propose_to_catalog(
    insumo_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Propone dar de alta este insumo propio en el catalogo publico."""
    ci = await _get_own(db, insumo_id, user)
    _require_editor(user)

    if ci.source_type == "catalog":
        raise HTTPException(400, "Este insumo ya proviene del catalogo publico")
    if ci.proposed_to_catalog:
        raise HTTPException(409, "Ya lo propusiste; esta en revision")

    sugerencia = await price_suggestions.suggest_new_insumo(
        db, company_insumo=ci, user_id=user.id,
    )
    if sugerencia is None:
        raise HTTPException(
            400,
            "Tu empresa tiene desactivado el aporte de datos al catalogo publico",
        )
    await db.commit()
    return {
        "ok": True,
        "data": {"suggestion_id": sugerencia.id, "state": sugerencia.state},
    }


# ── Cola de curacion (staff del portal) ────────────────────────
def _suggestion_dict(s: PriceSuggestion) -> dict:
    return {
        "id": s.id,
        "kind": s.kind,
        "insumo_id": s.insumo_id,
        "company_id": s.company_id,
        "name": s.name,
        "uom": s.uom,
        "category": s.category,
        "suggested_price": s.suggested_price,
        "current_price": s.current_price,
        "currency": s.currency,
        "region": s.region,
        "deviation_pct": s.deviation_pct,
        "z_score": s.z_score,
        "sample_count": s.sample_count,
        "source": s.source,
        "source_ref": s.source_ref,
        "state": s.state,
        "decision_reason": s.decision_reason,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None,
        "review_note": s.review_note,
    }


@router.get("/suggestions/queue")
async def suggestions_queue(
    state: str = Query("pending"),
    kind: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    if state not in SUGGESTION_STATES:
        raise HTTPException(400, f"Estado invalido: {', '.join(SUGGESTION_STATES)}")

    base = select(PriceSuggestion).where(PriceSuggestion.state == state)
    if kind:
        base = base.where(PriceSuggestion.kind == kind)
    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar() or 0
    rows = (await db.execute(
        base.order_by(PriceSuggestion.created_at.desc()).offset(offset).limit(limit)
    )).scalars().all()
    return {
        "ok": True,
        "data": [_suggestion_dict(s) for s in rows],
        "total": total,
        "stats": await price_suggestions.queue_stats(db),
    }


@router.post("/suggestions/{suggestion_id}/accept")
async def accept(
    suggestion_id: int,
    body: ReviewIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    s = await db.get(PriceSuggestion, suggestion_id)
    if s is None:
        raise HTTPException(404, "Sugerencia no encontrada")
    try:
        await price_suggestions.accept_suggestion(db, s, user.id, body.note)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    await db.commit()
    return {"ok": True, "data": _suggestion_dict(s)}


@router.post("/suggestions/{suggestion_id}/reject")
async def reject(
    suggestion_id: int,
    body: ReviewIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    s = await db.get(PriceSuggestion, suggestion_id)
    if s is None:
        raise HTTPException(404, "Sugerencia no encontrada")
    try:
        await price_suggestions.reject_suggestion(db, s, user.id, body.note)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    await db.commit()
    return {"ok": True, "data": _suggestion_dict(s)}


@router.get("/suggestions/config")
async def get_curation_config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    return {"ok": True, "data": await price_curation.get_config(db)}


@router.put("/suggestions/config")
async def set_curation_config(
    body: CurationConfigIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
):
    """Ajusta los umbrales de la compuerta sin tocar codigo."""
    from app.models.system_setting import SystemSetting

    actual = await price_curation.get_config(db)
    actual.update(body.model_dump(exclude_unset=True, exclude_none=True))

    row = await db.get(SystemSetting, price_curation.SETTING_KEY)
    if row is None:
        row = SystemSetting(key=price_curation.SETTING_KEY, value=actual)
        db.add(row)
    else:
        row.value = actual
    await db.commit()
    return {"ok": True, "data": actual}
