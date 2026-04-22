"""Plantillas de respuesta rapida para el inbox (5.4).

Permite al operador guardar mensajes frecuentes y reutilizarlos en el
composer. scope='global' => visible para todos; scope='personal' =>
solo el owner.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class InboxTemplate(Base):
    __tablename__ = "mkt_inbox_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default="personal", index=True,
    )  # "global" | "personal"
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<InboxTemplate {self.id} {self.scope} {self.title!r}>"
