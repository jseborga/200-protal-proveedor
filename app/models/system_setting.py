"""Configuracion global del sistema (key-value)."""

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class SystemSetting(TimestampMixin, Base):
    """Par clave-valor para configuracion del sistema."""

    __tablename__ = "mkt_system_setting"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<SystemSetting {self.key}>"
