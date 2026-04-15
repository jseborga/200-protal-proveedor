from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, get_current_user_optional
from app.models.insumo import Insumo, InsumoRegionalPrice
from app.models.price_history import PriceHistory
from app.models.user import User

router = APIRouter()


# ── Schemas ─────────────────────────────────────────────────────
class InsumoCreate(BaseModel):
    name: str
    code: str | None = None
    uom: str
    category: str | None = None
    subcategory: str | None = None
    description: str | None = None
    ref_price: float | None = None
    ref_currency: str = "BOB"


class InsumoUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    uom: str | None = None
    category: str | None = None
    subcategory: str | None = None
    description: str | None = None
    ref_price: float | None = None
    is_active: bool | None = None


class RegionalPriceInput(BaseModel):
    region: str
    price: float
    currency: str = "BOB"
    source: str | None = None


# ── Public endpoints (precios publicos) ─────────────────────────
@router.get("/public")
async def public_prices(
    q: str | None = Query(None),
    category: str | None = Query(None),
    region: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Public price list — no auth required."""
    query = select(Insumo).where(Insumo.is_active == True)
    if q:
        query = query.where(Insumo.name.ilike(f"%{q}%"))
    if category:
        query = query.where(Insumo.category == category)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(query.order_by(Insumo.name).offset(offset).limit(limit))
    insumos = result.scalars().all()

    data = []
    for ins in insumos:
        d = _insumo_to_dict(ins)
        if region:
            rp = await db.execute(
                select(InsumoRegionalPrice).where(
                    InsumoRegionalPrice.insumo_id == ins.id,
                    InsumoRegionalPrice.region == region,
                )
            )
            regional = rp.scalar_one_or_none()
            d["regional_price"] = regional.price if regional else None
        data.append(d)

    return {"ok": True, "data": data, "total": total}


@router.get("/public/search")
async def search_prices(
    q: str = Query(..., min_length=2),
    region: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Trigram similarity search on insumo names — public."""
    result = await db.execute(
        text("""
            SELECT id, name, uom, category, ref_price,
                   similarity(name_normalized, :q) AS sim
            FROM mkt_insumo
            WHERE is_active = true
              AND similarity(name_normalized, :q) > 0.15
            ORDER BY sim DESC
            LIMIT :lim
        """),
        {"q": q.lower(), "lim": limit},
    )
    rows = result.mappings().all()

    return {
        "ok": True,
        "data": [
            {
                "id": r["id"],
                "name": r["name"],
                "uom": r["uom"],
                "category": r["category"],
                "ref_price": r["ref_price"],
                "similarity": round(r["sim"], 3),
            }
            for r in rows
        ],
    }


# ── Authenticated endpoints ─────────────────────────────────────
@router.get("")
async def list_insumos(
    q: str | None = Query(None),
    category: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Insumo).where(Insumo.is_active == True)
    if q:
        query = query.where(Insumo.name.ilike(f"%{q}%"))
    if category:
        query = query.where(Insumo.category == category)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(query.order_by(Insumo.name).offset(offset).limit(limit))
    insumos = result.scalars().all()

    return {"ok": True, "data": [_insumo_to_dict(i) for i in insumos], "total": total}


@router.get("/{insumo_id}")
async def get_insumo(
    insumo_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    insumo = await db.get(Insumo, insumo_id)
    if not insumo:
        raise HTTPException(status_code=404, detail="Insumo no encontrado")

    # Include regional prices
    rp_result = await db.execute(
        select(InsumoRegionalPrice).where(InsumoRegionalPrice.insumo_id == insumo_id)
    )
    regional = rp_result.scalars().all()

    data = _insumo_to_dict(insumo)
    data["regional_prices"] = [
        {
            "id": rp.id,
            "region": rp.region,
            "price": rp.price,
            "currency": rp.currency,
            "source": rp.source,
            "sample_count": rp.sample_count,
            "confidence": rp.confidence,
        }
        for rp in regional
    ]
    return {"ok": True, "data": data}


@router.post("", status_code=201)
async def create_insumo(
    body: InsumoCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
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
    return {"ok": True, "data": _insumo_to_dict(insumo)}


@router.put("/{insumo_id}")
async def update_insumo(
    insumo_id: int,
    body: InsumoUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    insumo = await db.get(Insumo, insumo_id)
    if not insumo:
        raise HTTPException(status_code=404, detail="Insumo no encontrado")

    update_data = body.model_dump(exclude_unset=True)
    if "name" in update_data:
        from app.services.matching import normalize_text
        update_data["name_normalized"] = normalize_text(update_data["name"])
    if "uom" in update_data:
        from app.services.matching import normalize_uom
        update_data["uom_normalized"] = normalize_uom(update_data["uom"])

    for field, value in update_data.items():
        setattr(insumo, field, value)
    await db.flush()
    return {"ok": True, "data": _insumo_to_dict(insumo)}


@router.post("/{insumo_id}/regional-price")
async def add_regional_price(
    insumo_id: int,
    body: RegionalPriceInput,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    insumo = await db.get(Insumo, insumo_id)
    if not insumo:
        raise HTTPException(status_code=404, detail="Insumo no encontrado")

    # Upsert
    existing = await db.execute(
        select(InsumoRegionalPrice).where(
            InsumoRegionalPrice.insumo_id == insumo_id,
            InsumoRegionalPrice.region == body.region,
            InsumoRegionalPrice.currency == body.currency,
        )
    )
    rp = existing.scalar_one_or_none()
    if rp:
        rp.price = body.price
        rp.source = body.source
        rp.sample_count += 1
    else:
        rp = InsumoRegionalPrice(
            insumo_id=insumo_id,
            region=body.region,
            price=body.price,
            currency=body.currency,
            source=body.source,
        )
        db.add(rp)
    await db.flush()

    return {"ok": True}


@router.get("/categories/list")
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Insumo.category, func.count(Insumo.id))
        .where(Insumo.is_active == True, Insumo.category.isnot(None))
        .group_by(Insumo.category)
        .order_by(Insumo.category)
    )
    return {"ok": True, "data": [{"name": r[0], "count": r[1]} for r in result.all()]}


@router.get("/regions/list")
async def list_regions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(InsumoRegionalPrice.region, func.count(InsumoRegionalPrice.id))
        .group_by(InsumoRegionalPrice.region)
        .order_by(InsumoRegionalPrice.region)
    )
    return {"ok": True, "data": [{"name": r[0], "count": r[1]} for r in result.all()]}


# ── Price History (authenticated, for admin panel) ─────────────
@router.get("/{insumo_id}/history")
async def get_insumo_price_history(
    insumo_id: int,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Price history records for an insumo, newest first."""
    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.insumo_id == insumo_id)
        .order_by(PriceHistory.observed_date.desc())
        .limit(limit)
    )
    records = result.scalars().all()
    return {
        "ok": True,
        "data": [
            {
                "id": r.id,
                "unit_price": r.unit_price,
                "currency": r.currency,
                "quantity": r.quantity,
                "observed_date": r.observed_date.isoformat(),
                "source": r.source,
                "source_ref": r.source_ref,
                "supplier_id": r.supplier_id,
            }
            for r in records
        ],
    }


@router.get("/{insumo_id}/evolution")
async def get_insumo_price_evolution(
    insumo_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Price evolution by year: avg, min, max, median."""
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

    # Also get total count
    total = (await db.execute(
        select(func.count(PriceHistory.id)).where(PriceHistory.insumo_id == insumo_id)
    )).scalar() or 0

    return {
        "ok": True,
        "total_records": total,
        "evolution": [dict(r) for r in rows],
    }


@router.post("/{insumo_id}/refresh-price")
async def refresh_ref_price(
    insumo_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Recalculate ref_price from the median of last 12 months of price history."""
    insumo = await db.get(Insumo, insumo_id)
    if not insumo:
        raise HTTPException(status_code=404, detail="Insumo no encontrado")

    cutoff = date.today() - timedelta(days=365)
    result = await db.execute(
        text("""
            SELECT ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY unit_price)::numeric, 2) AS median_price,
                   COUNT(*) AS sample_count
            FROM mkt_price_history
            WHERE insumo_id = :insumo_id AND observed_date >= :cutoff
        """),
        {"insumo_id": insumo_id, "cutoff": cutoff},
    )
    row = result.mappings().first()

    if row and row["sample_count"] and row["sample_count"] > 0:
        insumo.ref_price = float(row["median_price"])
        await db.flush()
        return {
            "ok": True,
            "ref_price": insumo.ref_price,
            "sample_count": row["sample_count"],
            "period": f"ultimos 12 meses (desde {cutoff.isoformat()})",
        }

    # Fallback: use all-time median if no recent data
    result = await db.execute(
        text("""
            SELECT ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY unit_price)::numeric, 2) AS median_price,
                   COUNT(*) AS sample_count
            FROM mkt_price_history
            WHERE insumo_id = :insumo_id
        """),
        {"insumo_id": insumo_id},
    )
    row = result.mappings().first()
    if row and row["sample_count"] and row["sample_count"] > 0:
        insumo.ref_price = float(row["median_price"])
        await db.flush()
        return {
            "ok": True,
            "ref_price": insumo.ref_price,
            "sample_count": row["sample_count"],
            "period": "historico completo",
        }

    return {"ok": True, "ref_price": insumo.ref_price, "sample_count": 0, "period": "sin datos"}


# ── Helpers ─────────────────────────────────────────────────────
def _insumo_to_dict(i: Insumo) -> dict:
    return {
        "id": i.id,
        "name": i.name,
        "code": i.code,
        "uom": i.uom,
        "category": i.category,
        "subcategory": i.subcategory,
        "ref_price": i.ref_price,
        "ref_currency": i.ref_currency,
        "is_active": i.is_active,
    }
