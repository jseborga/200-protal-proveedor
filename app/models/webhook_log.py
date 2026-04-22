"""Historial de webhooks entrantes (Evolution / Telegram).

Se usa para mostrar el estado de salud de las integraciones en el admin
(\u00faltimo evento recibido por instancia, tipo de evento, conteo).

Pol\u00edtica de retenci\u00f3n: el helper record_webhook() mantiene los \u00faltimos
N=1000 rows por source (whatsapp|telegram) y borra el resto.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# En Postgres usamos JSONB (mejor indexaci\u00f3n); en SQLite (tests) JSON.
_JsonType = JSON().with_variant(JSONB, "postgresql")


class WebhookLog(Base):
    __tablename__ = "mkt_webhook_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
    )  # "whatsapp" | "telegram"
    event_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True,
    )  # p.ej. messages.upsert, connection.update
    instance_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="received",
    )  # received | processed | error
    payload: Mapped[dict | None] = mapped_column(_JsonType, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True,
    )

    def __repr__(self) -> str:
        return f"<WebhookLog {self.id} {self.source} {self.event_type} [{self.status}]>"
