"""Hub de conversaciones: sesiones cliente↔operador sobre un Pedido.

ConversationSession mantiene el estado de la conversacion para un Pedido:
que topic de Telegram la refleja, que operador esta atendiendo, y cuando fue
la ultima interaccion (para validar ventana 24h de WhatsApp).

Message es el log unificado de todos los mensajes que pasan por la sesion,
sin importar el canal (WA, TG, portal).
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger, DateTime, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class ConversationSession(TimestampMixin, Base):
    """Una conversacion activa entre cliente y operador sobre un Pedido."""

    __tablename__ = "mkt_conversation_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pedido_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_pedido.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="SET NULL"), nullable=True
    )
    client_phone: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    operator_id: Mapped[int | None] = mapped_column(
        ForeignKey("mkt_user.id", ondelete="SET NULL"), nullable=True
    )

    # Telegram bridge
    tg_group_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tg_topic_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="waiting_first_contact", index=True
    )  # waiting_first_contact, active, operator_engaged, quote_sent, closed

    last_client_msg_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_operator_msg_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 5.6: marcado explicito de "leido" por el operador
    operator_last_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 5.10: timestamp del ultimo auto-handoff (cooldown anti-ping-pong)
    last_handoff_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="session", cascade="all, delete-orphan",
        order_by="Message.id",
    )

    __table_args__ = (
        Index("ix_mkt_conv_session_phone_state", "client_phone", "state"),
    )

    def __repr__(self) -> str:
        return f"<ConversationSession {self.id} pedido={self.pedido_id} state={self.state}>"


class Message(TimestampMixin, Base):
    """Mensaje individual dentro de una ConversationSession (log unificado)."""

    __tablename__ = "mkt_conversation_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("mkt_conversation_session.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # inbound, outbound
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # whatsapp, telegram
    sender_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # client, operator, bot, system
    sender_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)  # phone, tg_user_id
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ext_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    session: Mapped["ConversationSession"] = relationship(
        "ConversationSession", back_populates="messages"
    )

    def __repr__(self) -> str:
        return f"<Message {self.id} {self.direction}/{self.channel} session={self.session_id}>"
