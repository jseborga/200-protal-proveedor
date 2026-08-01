"""Emision y resolucion de sugerencias de precio / alta de insumos.

Es el circuito que mantiene vivo el catalogo publico:

    empresa corrige un precio en su presupuesto
        -> se emite una sugerencia
        -> la compuerta estadistica decide (auto o revision)
        -> al aceptarse se escribe en el historico y se recalcula ref_price

Reglas que no hay que romper:

* Solo aporta la empresa que dio su consentimiento (`contributes_prices`).
* Nunca se publica el precio individual atribuible a una empresa: lo que se
  publica es la MEDIANA del historico, que necesita varias observaciones.
* Aceptar una sugerencia no escribe `ref_price` a mano: escribe una
  observacion y deja que el calculo por mediana haga su trabajo. Asi un dato
  aceptado por error no mueve el precio de golpe.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import price_curation

# Observaciones minimas antes de publicar un precio de referencia. Protege el
# anonimato: con una sola observacion, ref_price seria el precio de una
# empresa identificable.
MIN_OBSERVATIONS_TO_PUBLISH = 2


async def _company_contributes(db: AsyncSession, company_id: int | None) -> bool:
    if not company_id:
        return False
    from app.models.company import Company

    company = await db.get(Company, company_id)
    return bool(company and company.contributes_prices)


async def suggest_price_update(
    db: AsyncSession,
    *,
    insumo_id: int,
    suggested_price: float,
    company_id: int | None,
    user_id: int | None,
    source: str = "budget",
    source_ref: str | None = None,
    region: str | None = None,
    currency: str = "BOB",
):
    """Registra una propuesta de precio para un insumo del catalogo.

    Devuelve la sugerencia creada, o None si la empresa no aporta datos o el
    precio no aporta informacion (identico al vigente).
    """
    from app.models.company_insumo import PriceSuggestion
    from app.models.insumo import Insumo

    if not await _company_contributes(db, company_id):
        return None

    insumo = await db.get(Insumo, insumo_id)
    if insumo is None or not insumo.is_active:
        return None

    actual = insumo.ref_price
    if actual is not None and abs(suggested_price - actual) < 0.005:
        return None  # sin novedad, no ensuciar la cola

    verdict = await price_curation.evaluate_for_insumo(
        db, insumo_id, suggested_price, region,
    )

    sugerencia = PriceSuggestion(
        kind="price_update",
        insumo_id=insumo_id,
        company_id=company_id,
        suggested_by=user_id,
        name=insumo.name,
        uom=insumo.uom,
        category=insumo.category,
        suggested_price=suggested_price,
        currency=currency,
        region=region,
        current_price=actual,
        deviation_pct=verdict.deviation_pct,
        z_score=verdict.z_score,
        sample_count=verdict.sample_count,
        source=source,
        source_ref=source_ref,
        state=verdict.state,
        decision_reason=verdict.reason,
    )
    db.add(sugerencia)
    await db.flush()

    if verdict.state == "auto_accepted":
        await _apply_price_suggestion(db, sugerencia, reviewer_id=None)

    return sugerencia


async def suggest_new_insumo(
    db: AsyncSession,
    *,
    company_insumo,
    user_id: int | None,
    region: str | None = None,
):
    """Propone dar de alta en el catalogo un insumo propio de una empresa.

    Este es el aporte concreto por usar el portal gratis: quien descubre un
    material que falta, lo comparte.
    """
    from app.models.company_insumo import PriceSuggestion

    if not await _company_contributes(db, company_insumo.company_id):
        return None

    sugerencia = PriceSuggestion(
        kind="new_insumo",
        insumo_id=None,
        company_insumo_id=company_insumo.id,
        company_id=company_insumo.company_id,
        suggested_by=user_id,
        name=company_insumo.name,
        uom=company_insumo.uom,
        category=company_insumo.category,
        suggested_price=company_insumo.reference_price,
        currency=company_insumo.currency,
        region=region,
        state="pending",  # un alta SIEMPRE la mira un humano
        decision_reason="Alta de insumo nuevo: requiere revision humana",
        source="manual",
    )
    db.add(sugerencia)
    company_insumo.proposed_to_catalog = True
    await db.flush()
    return sugerencia


async def _recompute_ref_price(db: AsyncSession, insumo_id: int) -> float | None:
    """Recalcula ref_price por MEDIANA de las observaciones del ultimo ano.

    Se usa mediana y no promedio porque un outlier que sobrevivio a la
    curacion no debe arrastrar el precio publico. Y solo se publica con al
    menos dos observaciones, para no exponer el precio de una sola empresa.
    """
    from app.models.insumo import Insumo
    from app.models.price_history import PriceHistory

    desde = date.today().replace(year=date.today().year - 1)
    precios = (await db.execute(
        select(PriceHistory.unit_price).where(
            PriceHistory.insumo_id == insumo_id,
            PriceHistory.observed_date >= desde,
            PriceHistory.unit_price > 0,
        )
    )).scalars().all()

    if len(precios) < MIN_OBSERVATIONS_TO_PUBLISH:
        return None

    import statistics

    mediana = round(float(statistics.median(precios)), 2)
    insumo = await db.get(Insumo, insumo_id)
    if insumo is not None:
        insumo.ref_price = mediana
    return mediana


async def _apply_price_suggestion(db: AsyncSession, sugerencia, reviewer_id: int | None):
    """Materializa una sugerencia aceptada como observacion de precio."""
    from app.models.price_history import PriceHistory

    db.add(PriceHistory(
        insumo_id=sugerencia.insumo_id,
        supplier_id=None,
        unit_price=sugerencia.suggested_price,
        currency=sugerencia.currency,
        uom=sugerencia.uom,
        observed_date=date.today(),
        source="portal",
        source_ref=f"suggestion:{sugerencia.id}",
        notes=(
            f"Aporte curado (empresa {sugerencia.company_id}); "
            f"{sugerencia.decision_reason or ''}"[:500]
        ),
    ))
    await db.flush()
    await _recompute_ref_price(db, sugerencia.insumo_id)


async def accept_suggestion(db: AsyncSession, sugerencia, reviewer_id: int, note: str | None = None):
    """Acepta una sugerencia pendiente."""
    from app.models.insumo import Insumo
    from app.services.matching import normalize_text, normalize_uom

    if sugerencia.state not in ("pending",):
        raise ValueError("La sugerencia ya fue resuelta")

    if sugerencia.kind == "new_insumo":
        # Alta en el catalogo publico + vinculo con el insumo de la empresa.
        insumo = Insumo(
            name=sugerencia.name,
            name_normalized=normalize_text(sugerencia.name or ""),
            uom=sugerencia.uom or "u",
            uom_normalized=normalize_uom(sugerencia.uom or "u"),
            category=sugerencia.category,
            ref_price=None,  # se publica cuando haya observaciones suficientes
            ref_currency=sugerencia.currency,
            is_active=True,
        )
        db.add(insumo)
        await db.flush()
        sugerencia.insumo_id = insumo.id

        if sugerencia.company_insumo_id:
            from app.models.company_insumo import CompanyInsumo

            ci = await db.get(CompanyInsumo, sugerencia.company_insumo_id)
            if ci is not None:
                ci.source_type = "catalog"
                ci.source_insumo_id = insumo.id
                ci.proposed_to_catalog = False

    await _apply_price_suggestion(db, sugerencia, reviewer_id)

    sugerencia.state = "accepted"
    sugerencia.reviewed_by = reviewer_id
    sugerencia.reviewed_at = datetime.now(timezone.utc)
    sugerencia.review_note = note
    return sugerencia


async def reject_suggestion(db: AsyncSession, sugerencia, reviewer_id: int, note: str | None = None):
    if sugerencia.state not in ("pending",):
        raise ValueError("La sugerencia ya fue resuelta")
    sugerencia.state = "rejected"
    sugerencia.reviewed_by = reviewer_id
    sugerencia.reviewed_at = datetime.now(timezone.utc)
    sugerencia.review_note = note
    if sugerencia.company_insumo_id:
        from app.models.company_insumo import CompanyInsumo

        ci = await db.get(CompanyInsumo, sugerencia.company_insumo_id)
        if ci is not None:
            ci.proposed_to_catalog = False
    return sugerencia


async def queue_stats(db: AsyncSession) -> dict:
    """Resumen de la cola, para el panel de curacion."""
    from app.models.company_insumo import PriceSuggestion

    rows = (await db.execute(
        select(PriceSuggestion.state, PriceSuggestion.kind, func.count(PriceSuggestion.id))
        .group_by(PriceSuggestion.state, PriceSuggestion.kind)
    )).all()
    out: dict[str, dict[str, int]] = {}
    for state, kind, count in rows:
        out.setdefault(state, {})[kind] = count
    return out
