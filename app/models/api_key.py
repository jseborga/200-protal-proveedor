from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ApiKey(TimestampMixin, Base):
    __tablename__ = "mkt_api_key"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False)  # first 8 chars for display
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Permissions
    scopes: Mapped[str] = mapped_column(
        String(500), nullable=False, default="read,write"
    )  # comma-separated: read, write, delete

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Tracking
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="SET NULL"), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:
        return f"<ApiKey {self.id} {self.key_prefix}... {self.name}>"
