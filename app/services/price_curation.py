"""Curacion de precios: decide que entra solo y que va a revision humana.

El portal gratuito se mantiene actualizado con los datos que aportan quienes
lo usan (una empresa que consigue una cotizacion real y corrige el precio de
un insumo). El problema evidente es que tambien llegan errores de tipeo,
pruebas y datos de mala calidad.

La compuerta usa la dispersion del historico del propio insumo:

    z = |precio_propuesto - media| / desviacion_estandar

- Si no hay historico suficiente no se puede juzgar -> revision humana.
- Si z esta dentro del umbral, el precio es coherente con lo que ya se sabe
  del insumo -> se acepta solo.
- Si se aparta, es un dato interesante PERO sospechoso -> revision humana.
  No se descarta: un cambio real de mercado tambien se ve asi, y es
  justamente lo que un curador quiere mirar.
- Un valor absurdo (ordenes de magnitud) se marca como probable error de
  tipeo, pero tampoco se tira solo: se deja al curador con el motivo.

Todos los umbrales se configuran en SystemSetting['price_curation'] para
poder endurecerlos o aflojarlos sin tocar codigo.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

SETTING_KEY = "price_curation"

DEFAULTS = {
    # Observaciones minimas para que la estadistica signifique algo.
    "min_samples": 3,
    # Desviaciones estandar toleradas para aceptar sin revision.
    "z_auto": 2.0,
    # Cuando el historico no tiene dispersion (todos el mismo precio), se usa
    # esta variacion porcentual como criterio.
    "pct_auto": 10.0,
    # Mas alla de esto se considera probable error de tipeo.
    "max_ratio": 10.0,
    # Ventana del historico considerada.
    "window_days": 365,
    # Interruptor general: en False, todo va a revision humana.
    "auto_accept_enabled": True,
}


@dataclass
class Verdict:
    """Resultado de evaluar un precio propuesto."""

    auto_accept: bool
    state: str          # auto_accepted | pending | rejected
    reason: str
    z_score: float | None = None
    deviation_pct: float | None = None
    sample_count: int = 0
    mean: float | None = None
    stdev: float | None = None


async def get_config(db: AsyncSession) -> dict:
    """Umbrales vigentes (defaults + lo que haya guardado el admin)."""
    from app.models.system_setting import SystemSetting

    cfg = dict(DEFAULTS)
    row = await db.get(SystemSetting, SETTING_KEY)
    if row and isinstance(row.value, dict):
        for key in DEFAULTS:
            if key in row.value and row.value[key] is not None:
                cfg[key] = row.value[key]
    return cfg


def evaluate(
    suggested_price: float,
    samples: list[float],
    config: dict | None = None,
) -> Verdict:
    """Decide si un precio propuesto se acepta solo o va a revision.

    `samples` son los precios observados del insumo en la ventana. Funcion
    pura: no toca la base, para poder probarla a fondo.
    """
    cfg = {**DEFAULTS, **(config or {})}

    if suggested_price is None or suggested_price <= 0:
        return Verdict(
            auto_accept=False,
            state="rejected",
            reason="El precio propuesto debe ser mayor que cero",
        )

    limpios = [float(s) for s in samples if s is not None and s > 0]
    n = len(limpios)

    if not cfg["auto_accept_enabled"]:
        return Verdict(
            auto_accept=False, state="pending", sample_count=n,
            reason="La aceptacion automatica esta desactivada",
        )

    if n < cfg["min_samples"]:
        return Verdict(
            auto_accept=False,
            state="pending",
            sample_count=n,
            reason=(
                f"Solo hay {n} observacion(es) previas; se necesitan "
                f"{cfg['min_samples']} para decidir de forma automatica"
            ),
        )

    media = statistics.fmean(limpios)
    desv = statistics.pstdev(limpios) if n > 1 else 0.0
    desviacion_pct = ((suggested_price - media) / media * 100.0) if media else None

    # Guardia de magnitud: un cero de mas no debe entrar solo aunque la
    # dispersion historica sea grande.
    if media > 0:
        ratio = suggested_price / media
        if ratio >= cfg["max_ratio"] or ratio <= 1.0 / cfg["max_ratio"]:
            return Verdict(
                auto_accept=False,
                state="pending",
                reason=(
                    f"El precio propuesto es {ratio:.1f}x la media historica "
                    f"({media:.2f}): probable error de tipeo"
                ),
                deviation_pct=desviacion_pct,
                sample_count=n,
                mean=media,
                stdev=desv,
            )

    # Historico sin dispersion: se juzga por variacion porcentual.
    if desv <= 0:
        dentro = abs(desviacion_pct or 0.0) <= cfg["pct_auto"]
        return Verdict(
            auto_accept=dentro,
            state="auto_accepted" if dentro else "pending",
            reason=(
                f"Historico sin dispersion; variacion de "
                f"{abs(desviacion_pct or 0.0):.1f}% "
                f"({'dentro del' if dentro else 'supera el'} "
                f"{cfg['pct_auto']}% tolerado)"
            ),
            deviation_pct=desviacion_pct,
            sample_count=n,
            mean=media,
            stdev=0.0,
        )

    z = abs(suggested_price - media) / desv
    dentro = z <= cfg["z_auto"]
    return Verdict(
        auto_accept=dentro,
        state="auto_accepted" if dentro else "pending",
        reason=(
            f"Se aparta {z:.2f} desviaciones de la media historica "
            f"({media:.2f} +/- {desv:.2f}, {n} observaciones); "
            f"{'dentro del' if dentro else 'supera el'} umbral de {cfg['z_auto']}"
        ),
        z_score=round(z, 3),
        deviation_pct=desviacion_pct,
        sample_count=n,
        mean=media,
        stdev=desv,
    )


async def load_samples(
    db: AsyncSession,
    insumo_id: int,
    window_days: int = 365,
    region: str | None = None,
) -> list[float]:
    """Precios observados del insumo en la ventana, para juzgar uno nuevo."""
    from app.models.price_history import PriceHistory

    desde = (datetime.now(timezone.utc) - timedelta(days=window_days)).date()
    query = select(PriceHistory.unit_price).where(
        PriceHistory.insumo_id == insumo_id,
        PriceHistory.observed_date >= desde,
        PriceHistory.unit_price > 0,
    )
    rows = (await db.execute(query)).scalars().all()
    return [float(r) for r in rows]


async def evaluate_for_insumo(
    db: AsyncSession,
    insumo_id: int,
    suggested_price: float,
    region: str | None = None,
) -> Verdict:
    """Evalua un precio contra el historico real del insumo."""
    cfg = await get_config(db)
    samples = await load_samples(db, insumo_id, cfg["window_days"], region)
    return evaluate(suggested_price, samples, cfg)
