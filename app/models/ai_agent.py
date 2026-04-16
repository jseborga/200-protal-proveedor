"""Agentes de IA configurables del sistema."""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class AIAgent(TimestampMixin, Base):
    """Un agente de IA con rol, modelo y configuracion propios."""

    __tablename__ = "mkt_ai_agent"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # searcher, updater, matcher, orchestrator, communicator, claude_code

    # AI config — can override global or use global
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Channels & triggers
    channels: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # e.g. {"whatsapp": true, "telegram": true, "facebook": false, "webhook": true}

    triggers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # e.g. {"on_new_quotation": true, "on_price_update": false, "cron": "0 4 * * *"}

    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # e.g. {"max_tokens": 4000, "temperature": 0.3, "tools": [...]}

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<AIAgent {self.id} {self.name} ({self.agent_type})>"
