"""Notificaciones in-app para usuarios."""

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Notification(Base):
    """Notificacion in-app."""

    __tablename__ = "mkt_notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True,
    )  # pedido_completed, pedido_assigned, price_found, member_added, suggestion_approved, subscription_updated
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Notification {self.id} [{self.type}] user={self.user_id}>"
