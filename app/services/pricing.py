"""Analisis estadistico de precios con validacion humana.

Calcula estadisticas sobre precios recibidos en cotizaciones,
genera sugerencias de precio y actualiza la base centralizada.
"""

import statistics
from dataclasses import dataclass

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.insumo import Insumo, InsumoRegionalPrice
from app.models.quotation import QuotationLine


@dataclass
class PriceAnalysis:
    insumo_id: int
    region: str | None
    sample_count: int
    min_price: float
    max_price: float
    avg_price: float
    median_price: float
    trimmed_avg: float
    std_dev: float
    coeff_variation: float
    suggested_price: float
    confidence: float


async def analyze_insumo_prices(
    db: AsyncSession,
    insumo_id: int,
    region: str | None = None,
) -> PriceAnalysis | None:
    """Compute price statistics for a specific insumo from matched quotation lines."""
    query = (
        select(QuotationLine.unit_price)
        .where(
            QuotationLine.insumo_id == insumo_id,
            QuotationLine.match_state.in_(["auto_matched", "validated", "manual"]),
            QuotationLine.unit_price > 0,
        )
    )

    if region:
        from app.models.quotation import Quotation
        query = query.join(Quotation).where(Quotation.region == region)

    result = await db.execute(query)
    prices = [row[0] for row in result.all()]

    if len(prices) < 2:
        return None

    analysis = _compute_stats(insumo_id, region, prices)
    return analysis


def _compute_stats(
    insumo_id: int, region: str | None, prices: list[float]
) -> PriceAnalysis:
    """Pure statistical computation."""
    n = len(prices)
    sorted_prices = sorted(prices)

    min_p = sorted_prices[0]
    max_p = sorted_prices[-1]
    avg_p = statistics.mean(prices)
    median_p = statistics.median(prices)
    std_dev = statistics.stdev(prices) if n > 1 else 0.0
    coeff_var = (std_dev / avg_p * 100) if avg_p > 0 else 0.0

    # Trimmed average: remove IQR outliers
    trimmed = _trimmed_average(sorted_prices)

    # Confidence based on sample size and consistency
    confidence = _compute_confidence(n, coeff_var)

    # Suggested price: weighted combination
    suggested = trimmed * 0.6 + median_p * 0.4

    return PriceAnalysis(
        insumo_id=insumo_id,
        region=region,
        sample_count=n,
        min_price=round(min_p, 2),
        max_price=round(max_p, 2),
        avg_price=round(avg_p, 2),
        median_price=round(median_p, 2),
        trimmed_avg=round(trimmed, 2),
        std_dev=round(std_dev, 2),
        coeff_variation=round(coeff_var, 2),
        suggested_price=round(suggested, 2),
        confidence=round(confidence, 3),
    )


def _trimmed_average(sorted_prices: list[float]) -> float:
    """Average after removing IQR outliers."""
    n = len(sorted_prices)
    if n < 4:
        return statistics.mean(sorted_prices)

    q1_idx = n // 4
    q3_idx = 3 * n // 4
    q1 = sorted_prices[q1_idx]
    q3 = sorted_prices[q3_idx]
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    filtered = [p for p in sorted_prices if lower <= p <= upper]
    return statistics.mean(filtered) if filtered else statistics.mean(sorted_prices)


def _compute_confidence(sample_count: int, coeff_variation: float) -> float:
    """Confidence score [0..1] based on sample size and price consistency."""
    # Size factor: more samples = more confident, diminishing returns
    size_factor = min(1.0, sample_count / 10)

    # Consistency factor: lower variation = more confident
    if coeff_variation < 10:
        consistency = 1.0
    elif coeff_variation < 25:
        consistency = 0.8
    elif coeff_variation < 50:
        consistency = 0.5
    else:
        consistency = 0.3

    return size_factor * 0.5 + consistency * 0.5


async def update_reference_prices(
    db: AsyncSession,
    insumo_id: int,
    region: str | None = None,
) -> bool:
    """Recompute and update reference prices for an insumo."""
    analysis = await analyze_insumo_prices(db, insumo_id, region)
    if not analysis:
        return False

    insumo = await db.get(Insumo, insumo_id)
    if not insumo:
        return False

    # Update global reference price (if no region or high confidence)
    if not region or analysis.confidence > 0.7:
        insumo.ref_price = analysis.suggested_price

    # Update regional price
    if region:
        existing = await db.execute(
            select(InsumoRegionalPrice).where(
                InsumoRegionalPrice.insumo_id == insumo_id,
                InsumoRegionalPrice.region == region,
            )
        )
        rp = existing.scalar_one_or_none()
        if rp:
            rp.price = analysis.suggested_price
            rp.sample_count = analysis.sample_count
            rp.confidence = analysis.confidence
            rp.source = "analysis"
        else:
            rp = InsumoRegionalPrice(
                insumo_id=insumo_id,
                region=region,
                price=analysis.suggested_price,
                sample_count=analysis.sample_count,
                confidence=analysis.confidence,
                source="analysis",
            )
            db.add(rp)

    await db.flush()
    return True


async def bulk_update_prices(db: AsyncSession, region: str | None = None) -> dict:
    """Recompute prices for all insumos with matched quotation lines."""
    # Find insumos that have matched lines
    result = await db.execute(
        select(func.distinct(QuotationLine.insumo_id)).where(
            QuotationLine.insumo_id.isnot(None),
            QuotationLine.match_state.in_(["auto_matched", "validated", "manual"]),
        )
    )
    insumo_ids = [row[0] for row in result.all()]

    updated = 0
    skipped = 0
    for insumo_id in insumo_ids:
        if await update_reference_prices(db, insumo_id, region):
            updated += 1
        else:
            skipped += 1

    return {"updated": updated, "skipped": skipped, "total": len(insumo_ids)}
