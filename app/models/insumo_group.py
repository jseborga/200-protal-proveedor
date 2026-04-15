from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class InsumoGroup(TimestampMixin, Base):
    """Agrupacion de insumos por familia (ej: Pintura Latex, Acero Corrugado)."""

    __tablename__ = "mkt_insumo_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name_normalized: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    variant_label: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # "Color", "Diametro", "Medida", etc.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    insumos: Mapped[list["Insumo"]] = relationship(
        "Insumo", back_populates="group"
    )

    def __repr__(self) -> str:
        return f"<InsumoGroup {self.id} {self.name}>"
