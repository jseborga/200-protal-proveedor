"""Biblioteca de insumos propia de cada empresa y circuito de curacion.

Espeja el diseno multiempresa de Odoo:

    portal                 Odoo
    -------------------    ---------------------------
    CompanyInsumo          apu.company.insumo
    PriceSuggestion        apu.price.suggestion

Idea del circuito:

1. Una empresa arma presupuestos con insumos del catalogo central (publico)
   o con los suyos propios. Los suyos NUNCA se ven desde otra empresa.
2. Cuando alguien cambia a mano el precio de un insumo del catalogo, ese dato
   vale: significa que consiguio una cotizacion real. Se emite una sugerencia.
3. Cuando una empresa crea un insumo que no existe en el catalogo, puede
   proponerlo para darlo de alta. Ese es el aporte por usar el portal gratis.
4. Las sugerencias pasan por una compuerta estadistica: si el precio cae
   dentro de la variacion normal del historico se aceptan solas; si se
   desvia, van a revision humana. Ver `app/services/price_curation.py`.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

# Origen del precio de un insumo de empresa.
SOURCE_TYPES = ("manual", "catalog")

# Que propone una sugerencia.
SUGGESTION_KINDS = ("price_update", "new_insumo")

# Estados. `auto_accepted` se distingue de `accepted` para poder auditar
# cuanto entro sin ojo humano y ajustar los umbrales.
SUGGESTION_STATES = ("pending", "auto_accepted", "accepted", "rejected")

# De donde salio el dato.
SUGGESTION_SOURCES = ("budget", "quotation", "pedido", "import", "manual")


class CompanyInsumo(TimestampMixin, Base):
    """Insumo maestro de una empresa.

    Puede ser propio (source_type='manual') o una copia vinculada a un insumo
    del catalogo central (source_type='catalog' + source_insumo_id), que es
    lo que permite refrescar su precio desde el mercado.
    """

    __tablename__ = "mkt_company_insumo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_company.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # mat | mo | eq | sub, igual que las lineas de APU.
    type: Mapped[str] = mapped_column(String(10), default="mat", nullable=False)
    uom: Mapped[str] = mapped_column(String(30), default="u", nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    reference_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="BOB", nullable=False)

    source_type: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    source_insumo_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_insumo.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    last_price_update: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Se propuso para el catalogo publico y aun no se resolvio.
    proposed_to_catalog: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        # El codigo, si se usa, es unico DENTRO de la empresa.
        UniqueConstraint("company_id", "code", name="uq_company_insumo_code"),
        Index("ix_company_insumo_lookup", "company_id", "type", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<CompanyInsumo {self.id} c{self.company_id} {self.name[:30]}>"


class PriceSuggestion(TimestampMixin, Base):
    """Propuesta de precio (o de alta de insumo) para el catalogo publico.

    Es el mecanismo por el que el portal gratuito se mantiene actualizado sin
    que nadie escriba directamente sobre el catalogo.
    """

    __tablename__ = "mkt_price_suggestion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    kind: Mapped[str] = mapped_column(
        String(20), default="price_update", nullable=False, index=True,
    )
    # Nulo cuando kind='new_insumo': todavia no existe en el catalogo.
    insumo_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_insumo.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    company_insumo_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_company_insumo.id", ondelete="SET NULL"), nullable=True,
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_company.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    suggested_by: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="SET NULL"), nullable=True,
    )

    # Datos propuestos. Para new_insumo describen el insumo a crear.
    name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uom: Mapped[str | None] = mapped_column(String(30), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    suggested_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="BOB", nullable=False)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Foto del estado del catalogo al momento de proponer.
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    deviation_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Cuantas desviaciones estandar se aparta del historico. Es el numero que
    # decide si entra sola o va a revision.
    z_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    source: Mapped[str] = mapped_column(String(20), default="budget", nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)

    state: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True,
    )
    # Motivo por el que la compuerta decidio lo que decidio (auditable).
    decision_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)

    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="SET NULL"), nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_price_suggestion_queue", "state", "kind", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<PriceSuggestion {self.id} {self.kind} {self.state}>"
