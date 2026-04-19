from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "mkt_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user"
    )  # admin, manager, user, supplier
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_user_id: Mapped[str | None] = mapped_column(
        String(50), unique=True, nullable=True, index=True
    )

    # Company membership (Phase 2)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_company.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    company_role: Mapped[str | None] = mapped_column(
        String(30), nullable=True,
    )  # company_admin, cotizador, viewer

    # Relationships
    supplier: Mapped["Supplier | None"] = relationship(
        "Supplier", back_populates="user", uselist=False
    )
    company: Mapped["Company | None"] = relationship(
        "Company", back_populates="members", foreign_keys=[company_id],
    )

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email}>"


# Avoid circular imports
from .company import Company  # noqa: E402, F401
