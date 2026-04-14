from sqlalchemy import (
    Boolean, Float, ForeignKey, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class ProductMatch(TimestampMixin, Base):
    """Vinculo recordado entre un nombre de proveedor y un insumo estandarizado."""

    __tablename__ = "mkt_product_match"
    __table_args__ = (
        UniqueConstraint(
            "supplier_id", "product_name_normalized", "insumo_id",
            name="uq_supplier_product_insumo",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_supplier.id", ondelete="CASCADE"), nullable=False, index=True
    )
    insumo_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_insumo.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Original supplier text
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_name_normalized: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    uom_original: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Match quality
    method: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # remembered, exact, trigram, fuzzy, manual
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # 0..1
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    validated_by: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="SET NULL"), nullable=True
    )
    usage_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationships
    supplier: Mapped["Supplier"] = relationship("Supplier")
    insumo: Mapped["Insumo"] = relationship("Insumo", back_populates="matches")

    def __repr__(self) -> str:
        return f"<ProductMatch {self.product_name} → Insumo#{self.insumo_id} ({self.confidence:.0%})>"
