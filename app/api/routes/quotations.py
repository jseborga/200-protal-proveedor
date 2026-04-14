import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.quotation import Quotation, QuotationLine
from app.models.user import User

router = APIRouter()


# ── Schemas ─────────────────────────────────────────────────────
class QuotationLineInput(BaseModel):
    product_name: str
    product_code: str | None = None
    uom: str | None = None
    unit_price: float
    brand: str | None = None
    notes: str | None = None


class QuotationCreate(BaseModel):
    supplier_id: int
    currency: str = "BOB"
    region: str | None = None
    notes: str | None = None
    valid_until: datetime | None = None
    lines: list[QuotationLineInput]


class QuotationLineUpdate(BaseModel):
    insumo_id: int | None = None
    match_state: str | None = None
    price_suggestion_state: str | None = None


# ── Endpoints ───────────────────────────────────────────────────
@router.get("")
async def list_quotations(
    supplier_id: int | None = Query(None),
    state: str | None = Query(None),
    source: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Quotation)
    if supplier_id:
        query = query.where(Quotation.supplier_id == supplier_id)
    if state:
        query = query.where(Quotation.state == state)
    if source:
        query = query.where(Quotation.source == source)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(
        query.order_by(Quotation.created_at.desc()).offset(offset).limit(limit)
    )
    quotations = result.scalars().all()

    return {
        "ok": True,
        "data": [_quot_to_dict(q) for q in quotations],
        "total": total,
    }


@router.get("/{quotation_id}")
async def get_quotation(
    quotation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Quotation)
        .where(Quotation.id == quotation_id)
        .options(selectinload(Quotation.lines))
    )
    quotation = result.scalar_one_or_none()
    if not quotation:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")

    data = _quot_to_dict(quotation)
    data["lines"] = [_line_to_dict(l) for l in quotation.lines]
    return {"ok": True, "data": data}


@router.post("", status_code=201)
async def create_quotation(
    body: QuotationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ref = f"COT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    quotation = Quotation(
        reference=ref,
        supplier_id=body.supplier_id,
        currency=body.currency,
        region=body.region,
        notes=body.notes,
        valid_until=body.valid_until,
        source="portal",
        state="received",
        received_at=datetime.now(timezone.utc),
        line_count=len(body.lines),
    )
    db.add(quotation)
    await db.flush()

    for i, line_data in enumerate(body.lines):
        line = QuotationLine(
            quotation_id=quotation.id,
            sequence=i,
            **line_data.model_dump(),
        )
        db.add(line)
    await db.flush()

    return {"ok": True, "data": _quot_to_dict(quotation)}


@router.post("/{quotation_id}/process")
async def process_quotation(
    quotation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Trigger matching engine on a quotation's lines."""
    quotation = await db.get(Quotation, quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Cotizacion no encontrada")

    quotation.state = "processing"
    await db.flush()

    # Matching will be handled by the matching service
    from app.services.matching import run_matching
    matched = await run_matching(db, quotation_id)

    quotation.state = "matched"
    quotation.matched_count = matched
    await db.flush()

    return {"ok": True, "matched": matched}


@router.put("/{quotation_id}/lines/{line_id}")
async def update_quotation_line(
    quotation_id: int,
    line_id: int,
    body: QuotationLineUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    line = await db.get(QuotationLine, line_id)
    if not line or line.quotation_id != quotation_id:
        raise HTTPException(status_code=404, detail="Linea no encontrada")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(line, field, value)
    await db.flush()
    return {"ok": True, "data": _line_to_dict(line)}


@router.post("/upload")
async def upload_quotation(
    supplier_id: int = Form(...),
    file: UploadFile = File(...),
    region: str | None = Form(None),
    currency: str = Form("BOB"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload Excel/PDF/image for AI extraction."""
    content = await file.read()
    filename = file.filename or "upload"
    content_type = file.content_type or ""

    # Determine source type
    if "excel" in content_type or filename.endswith((".xlsx", ".xls")):
        source = "excel"
    elif "pdf" in content_type or filename.endswith(".pdf"):
        source = "pdf"
    elif content_type.startswith("image/"):
        source = "photo"
    else:
        raise HTTPException(status_code=400, detail="Formato no soportado. Use Excel, PDF o imagen.")

    from app.services.ai_extract import extract_quotation_data
    extracted = await extract_quotation_data(content, filename, source)

    if not extracted or not extracted.get("lines"):
        raise HTTPException(status_code=422, detail="No se pudieron extraer datos del archivo")

    ref = f"COT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    quotation = Quotation(
        reference=ref,
        supplier_id=supplier_id,
        currency=currency,
        region=region,
        source=source,
        state="received",
        received_at=datetime.now(timezone.utc),
        original_file=filename,
        ai_extraction=extracted.get("metadata"),
        line_count=len(extracted["lines"]),
    )
    db.add(quotation)
    await db.flush()

    for i, item in enumerate(extracted["lines"]):
        line = QuotationLine(
            quotation_id=quotation.id,
            sequence=i,
            product_name=item.get("name", "Sin nombre"),
            product_code=item.get("code"),
            uom=item.get("uom"),
            unit_price=float(item.get("price", 0)),
            brand=item.get("brand"),
        )
        db.add(line)
    await db.flush()

    return {
        "ok": True,
        "data": _quot_to_dict(quotation),
        "extracted_lines": len(extracted["lines"]),
    }


# ── Helpers ─────────────────────────────────────────────────────
def _quot_to_dict(q: Quotation) -> dict:
    return {
        "id": q.id,
        "reference": q.reference,
        "supplier_id": q.supplier_id,
        "state": q.state,
        "source": q.source,
        "currency": q.currency,
        "region": q.region,
        "line_count": q.line_count,
        "matched_count": q.matched_count,
        "valid_until": q.valid_until.isoformat() if q.valid_until else None,
        "received_at": q.received_at.isoformat() if q.received_at else None,
        "created_at": q.created_at.isoformat() if q.created_at else None,
    }


def _line_to_dict(l: QuotationLine) -> dict:
    return {
        "id": l.id,
        "sequence": l.sequence,
        "product_name": l.product_name,
        "product_code": l.product_code,
        "uom": l.uom,
        "unit_price": l.unit_price,
        "brand": l.brand,
        "insumo_id": l.insumo_id,
        "match_confidence": l.match_confidence,
        "match_method": l.match_method,
        "match_state": l.match_state,
        "price_suggestion_state": l.price_suggestion_state,
    }
