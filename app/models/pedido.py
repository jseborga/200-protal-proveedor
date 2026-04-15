"""Pedido de Cotizacion: solicitud de precios por proyecto."""

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Pedido(TimestampMixin, Base):
    """Solicitud de cotizacion para un proyecto."""

    __tablename__ = "mkt_pedido"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", index=True
    )  # draft, active, researching, completed, cancelled

    created_by: Mapped[int] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_to: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="SET NULL"), nullable=True
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_company.id", ondelete="SET NULL"), nullable=True, index=True,
    )

    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="BOB", nullable=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quotes_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    items: Mapped[list["PedidoItem"]] = relationship(
        "PedidoItem", back_populates="pedido", cascade="all, delete-orphan",
        order_by="PedidoItem.sequence",
    )
    creator: Mapped["User"] = relationship(
        "User", foreign_keys=[created_by], lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Pedido {self.id} {self.reference} [{self.state}]>"


class PedidoItem(TimestampMixin, Base):
    """Item dentro de un pedido de cotizacion."""

    __tablename__ = "mkt_pedido_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pedido_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_pedido.id", ondelete="CASCADE"), nullable=False, index=True
    )
    insumo_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_insumo.id", ondelete="SET NULL"), nullable=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    uom: Mapped[str | None] = mapped_column(String(30), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    ref_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    pedido: Mapped["Pedido"] = relationship("Pedido", back_populates="items")
    precios: Mapped[list["PedidoPrecio"]] = relationship(
        "PedidoPrecio", back_populates="pedido_item", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<PedidoItem {self.id} {self.name} x{self.quantity}>"


class PedidoPrecio(TimestampMixin, Base):
    """Precio encontrado para un item del pedido."""

    __tablename__ = "mkt_pedido_precio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pedido_item_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_pedido_item.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_supplier.id", ondelete="SET NULL"), nullable=True
    )
    supplier_name_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="BOB", nullable=False)
    source: Mapped[str] = mapped_column(
        String(20), default="manual", nullable=False
    )  # manual, platform_rfq, upload
    source_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    pedido_item: Mapped["PedidoItem"] = relationship("PedidoItem", back_populates="precios")

    def __repr__(self) -> str:
        return f"<PedidoPrecio {self.id} {self.unit_price} {self.currency}>"


# Avoid circular imports
from .user import User  # noqa: E402, F401
