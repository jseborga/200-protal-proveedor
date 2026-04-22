"""Suscripciones Web Push (5.5 VAPID).

Cada navegador/dispositivo del operador registra aqui su endpoint + claves
p256dh/auth. Al llegar un nuevo mensaje del cliente a una sesion asignada
(o sin asignar, si el usuario lo activa), el backend envia un push via
pywebpush a todos los endpoints activos del operador.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PushSubscription(Base):
    __tablename__ = "mkt_push_subscription"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # endpoint unico (clave natural para upsert)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    def __repr__(self) -> str:
        ep_short = (self.endpoint or "")[:48]
        return f"<PushSubscription {self.id} user={self.user_id} ep={ep_short}...>"
