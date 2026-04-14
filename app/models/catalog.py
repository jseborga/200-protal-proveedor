"""Tablas administrables para categorias de materiales y unidades de medida."""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Category(TimestampMixin, Base):
    """Categoria de materiales/proveedores, administrable desde el panel."""

    __tablename__ = "mkt_category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(30), nullable=True)  # HTML entity or emoji
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Category {self.key} ({self.label})>"


class UnitOfMeasure(TimestampMixin, Base):
    """Unidad de medida administrable, con aliases para el motor de matching."""

    __tablename__ = "mkt_uom"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    aliases: Mapped[list | None] = mapped_column(ARRAY(String(50)), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<UnitOfMeasure {self.key} ({self.label})>"
