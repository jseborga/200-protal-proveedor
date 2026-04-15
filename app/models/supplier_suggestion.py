"""Sugerencias de proveedores por usuarios."""

from datetime import datetime

from sqlalchemy import (
    DateTime, ForeignKey, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class SupplierSuggestion(TimestampMixin, Base):
    """Proveedor sugerido por un usuario para revision del admin."""

    __tablename__ = "mkt_supplier_suggestion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    suggested_by: Mapped[int] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_company.id", ondelete="SET NULL"), nullable=True,
    )

    # Supplier data
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(30), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    categories: Mapped[list | None] = mapped_column(ARRAY(String(50)), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Review
    state: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True,
    )  # pending, approved, rejected, duplicate
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="SET NULL"), nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_supplier.id", ondelete="SET NULL"), nullable=True,
    )

    # Relationships
    suggester: Mapped["User"] = relationship(
        "User", foreign_keys=[suggested_by], lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<SupplierSuggestion {self.id} {self.name} [{self.state}]>"


from .user import User  # noqa: E402, F401
