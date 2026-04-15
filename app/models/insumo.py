from sqlalchemy import (
    Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Insumo(TimestampMixin, Base):
    """Insumo estandarizado del catalogo centralizado."""

    __tablename__ = "mkt_insumo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name_normalized: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    uom: Mapped[str] = mapped_column(String(30), nullable=False)  # m3, kg, m2, pza, etc.
    uom_normalized: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Reference price (latest validated)
    ref_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_currency: Mapped[str] = mapped_column(String(3), default="BOB", nullable=False)

    # Matching helpers
    tokens: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # pre-computed tokens

    # Product grouping (family/variants)
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_insumo_group.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Relationships
    group: Mapped["InsumoGroup | None"] = relationship(
        "InsumoGroup", back_populates="insumos"
    )
    regional_prices: Mapped[list["InsumoRegionalPrice"]] = relationship(
        "InsumoRegionalPrice", back_populates="insumo", cascade="all, delete-orphan"
    )
    matches: Mapped[list["ProductMatch"]] = relationship(
        "ProductMatch", back_populates="insumo"
    )
    price_history: Mapped[list["PriceHistory"]] = relationship(
        "PriceHistory", back_populates="insumo", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Insumo {self.id} {self.name} [{self.uom}]>"


class InsumoRegionalPrice(TimestampMixin, Base):
    """Precio de referencia de un insumo por region."""

    __tablename__ = "mkt_insumo_regional_price"
    __table_args__ = (
        UniqueConstraint("insumo_id", "region", "currency", name="uq_insumo_region_currency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    insumo_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_insumo.id", ondelete="CASCADE"), nullable=False, index=True
    )
    region: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # e.g. "Santa Cruz", "La Paz"
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="BOB", nullable=False)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)  # quotation, manual, import
    sample_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)  # 0..1

    # Relationships
    insumo: Mapped["Insumo"] = relationship("Insumo", back_populates="regional_prices")

    def __repr__(self) -> str:
        return f"<InsumoRegionalPrice {self.insumo_id} {self.region} {self.price} {self.currency}>"
