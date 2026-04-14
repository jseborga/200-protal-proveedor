from datetime import datetime

from sqlalchemy import (
    DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Quotation(TimestampMixin, Base):
    """Cotizacion recibida de un proveedor."""

    __tablename__ = "mkt_quotation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_supplier.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rfq_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_rfq.id", ondelete="SET NULL"), nullable=True, index=True
    )
    state: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False, index=True
    )  # draft, received, processing, matched, validated, expired, cancelled
    source: Mapped[str] = mapped_column(
        String(20), default="portal", nullable=False
    )  # portal, excel, pdf, photo, whatsapp, telegram, api
    currency: Mapped[str] = mapped_column(String(3), default="BOB", nullable=False)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # AI extraction metadata
    ai_extraction: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    original_file: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Stats
    line_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="quotations")
    rfq: Mapped["RFQ | None"] = relationship("RFQ", back_populates="quotations")
    lines: Mapped[list["QuotationLine"]] = relationship(
        "QuotationLine", back_populates="quotation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Quotation {self.reference} [{self.state}]>"


class QuotationLine(TimestampMixin, Base):
    """Linea individual de una cotizacion."""

    __tablename__ = "mkt_quotation_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quotation_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_quotation.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Supplier-provided data
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    uom: Mapped[str | None] = mapped_column(String(30), nullable=True)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Match result
    insumo_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_insumo.id", ondelete="SET NULL"), nullable=True, index=True
    )
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..1
    match_method: Mapped[str | None] = mapped_column(String(20), nullable=True)  # remembered, exact, trigram, fuzzy
    match_state: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, auto_matched, validated, rejected, manual

    # Price suggestion
    price_suggestion_state: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, suggested, accepted, rejected

    # Relationships
    quotation: Mapped["Quotation"] = relationship("Quotation", back_populates="lines")
    insumo: Mapped["Insumo | None"] = relationship("Insumo")

    def __repr__(self) -> str:
        return f"<QuotationLine {self.id} {self.product_name} ${self.unit_price}>"
