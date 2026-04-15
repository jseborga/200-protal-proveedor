"""Empresa y Suscripcion."""

from datetime import datetime, date

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Plan(TimestampMixin, Base):
    """Plan de suscripcion configurable."""

    __tablename__ = "mkt_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    max_users: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_pedidos_month: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    price_bob: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    features: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "key": self.key,
            "label": self.label,
            "max_users": self.max_users,
            "max_pedidos_month": self.max_pedidos_month,
            "price_bob": self.price_bob,
            "features": self.features or [],
            "sort_order": self.sort_order,
            "is_active": self.is_active,
        }

    def __repr__(self) -> str:
        return f"<Plan {self.key} {self.label}>"


class Company(TimestampMixin, Base):
    """Empresa registrada en la plataforma."""

    __tablename__ = "mkt_company"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    nit: Mapped[str | None] = mapped_column(String(30), nullable=True, unique=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str] = mapped_column(String(10), default="BO", nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    subscription: Mapped["Subscription | None"] = relationship(
        "Subscription", back_populates="company", uselist=False,
    )
    members: Mapped[list["User"]] = relationship(
        "User", back_populates="company", foreign_keys="User.company_id",
    )

    def __repr__(self) -> str:
        return f"<Company {self.id} {self.name}>"


class Subscription(TimestampMixin, Base):
    """Suscripcion de una empresa."""

    __tablename__ = "mkt_subscription"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_company.id", ondelete="CASCADE"), nullable=False, unique=True, index=True,
    )
    plan: Mapped[str] = mapped_column(String(30), default="free", nullable=False)
    state: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False,
    )  # active, expired, cancelled, suspended
    max_users: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_pedidos_month: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    payment_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_payment_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_payment_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="subscription")

    def __repr__(self) -> str:
        return f"<Subscription {self.id} [{self.plan}] company={self.company_id}>"


# Avoid circular imports
from .user import User  # noqa: E402, F401
