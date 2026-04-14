from datetime import datetime

from sqlalchemy import (
    DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class RFQ(TimestampMixin, Base):
    """Solicitud de cotizacion enviada a proveedores."""

    __tablename__ = "mkt_rfq"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False, index=True
    )  # draft, sent, partial, closed, cancelled
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="SET NULL"), nullable=True
    )
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="BOB", nullable=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Delivery channels used
    channels_used: Mapped[list | None] = mapped_column(ARRAY(String(20)), nullable=True)

    # Target suppliers
    supplier_ids: Mapped[list | None] = mapped_column(ARRAY(Integer), nullable=True)
    supplier_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    response_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    items: Mapped[list["RFQItem"]] = relationship(
        "RFQItem", back_populates="rfq", cascade="all, delete-orphan"
    )
    quotations: Mapped[list["Quotation"]] = relationship(
        "Quotation", back_populates="rfq"
    )
    creator: Mapped["User | None"] = relationship("User")

    def __repr__(self) -> str:
        return f"<RFQ {self.reference} [{self.state}]>"


class RFQItem(TimestampMixin, Base):
    """Item solicitado en una RFQ."""

    __tablename__ = "mkt_rfq_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rfq_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_rfq.id", ondelete="CASCADE"), nullable=False, index=True
    )
    insumo_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_insumo.id", ondelete="SET NULL"), nullable=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    uom: Mapped[str | None] = mapped_column(String(30), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    ref_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    rfq: Mapped["RFQ"] = relationship("RFQ", back_populates="items")
    insumo: Mapped["Insumo | None"] = relationship("Insumo")

    def __repr__(self) -> str:
        return f"<RFQItem {self.id} {self.name}>"
