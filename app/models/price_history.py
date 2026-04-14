from datetime import date

from sqlalchemy import (
    Date, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class PriceHistory(TimestampMixin, Base):
    """Registro historico de precios observados por insumo y proveedor.

    Cada fila es una observacion de precio en una fecha especifica,
    permitiendo rastrear la evolucion de precios en el tiempo.
    """

    __tablename__ = "mkt_price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    insumo_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_insumo.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_supplier.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Price data
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="BOB", nullable=False)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    uom: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # When and where
    observed_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source: Mapped[str] = mapped_column(
        String(30), nullable=False, default="import"
    )  # pedido, cotizacion, manual, import
    source_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    insumo: Mapped["Insumo"] = relationship("Insumo", back_populates="price_history")
    supplier: Mapped["Supplier | None"] = relationship("Supplier")

    def __repr__(self) -> str:
        return f"<PriceHistory {self.insumo_id} {self.unit_price} {self.currency} @ {self.observed_date}>"
