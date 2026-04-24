"""Etiquetas manuales para sesiones del Conversation Hub (Fase 5.12).

Dos entidades:
- `Tag` (tabla `mkt_tag`): catalogo global de etiquetas reutilizables.
- `SessionTag` (tabla `mkt_session_tag`): junction sesion <-> tag.

La mutacion se restringe a MANAGER_ROLES en los endpoints; aqui solo se
define el schema.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


# Paleta fija de slugs permitidos. El frontend mapea cada slug a (bg, fg).
TAG_COLOR_SLUGS = (
    "slate", "blue", "green", "yellow", "red", "purple", "pink", "orange",
)


class Tag(TimestampMixin, Base):
    """Etiqueta global reutilizable en sesiones."""

    __tablename__ = "mkt_tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Nombre normalizado a lowercase en la capa de servicio.
    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="slate")
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<Tag {self.id} {self.name!r} color={self.color}>"


class SessionTag(Base):
    """Asociacion entre una ConversationSession y un Tag."""

    __tablename__ = "mkt_session_tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_conversation_session.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_tag.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    added_by: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="SET NULL"), nullable=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("session_id", "tag_id", name="uq_session_tag"),
        Index("ix_session_tag_session_tag", "session_id", "tag_id"),
    )

    def __repr__(self) -> str:
        return f"<SessionTag session={self.session_id} tag={self.tag_id}>"
