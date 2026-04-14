from sqlalchemy import (
    Boolean, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Supplier(TimestampMixin, Base):
    __tablename__ = "mkt_supplier"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    trade_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nit: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(30), nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(5), default="BO", nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Classification
    categories: Mapped[list | None] = mapped_column(ARRAY(String(50)), nullable=True)
    verification_state: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending, verified, rejected
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Stats (denormalized for fast queries)
    rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    quotation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_response_days: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Preferred channels for RFQ delivery
    preferred_channel: Mapped[str] = mapped_column(
        String(20), default="email", nullable=False
    )  # email, whatsapp, telegram

    # Extra data
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    user: Mapped["User | None"] = relationship("User", back_populates="supplier")
    quotations: Mapped[list["Quotation"]] = relationship(
        "Quotation", back_populates="supplier"
    )

    def __repr__(self) -> str:
        return f"<Supplier {self.id} {self.name}>"
