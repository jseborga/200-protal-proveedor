"""push_subscription + system_setting

Revision ID: 0001
Revises:
Create Date: 2026-04-22

Primera migracion formal del proyecto. Antes de este commit el schema se
creaba via `Base.metadata.create_all()` al startup (ver `app/main.py`) y
varios ALTER TABLE IF NOT EXISTS idempotentes para columnas agregadas
posteriormente.

Esta revision declara explicitamente las dos tablas agregadas en la
Fase 5 del Conversation Hub:

- `mkt_push_subscription` (5.5): suscripciones Web Push por usuario.
- `mkt_system_setting` (pre-existente usada por 5.7 para guardar la
  config de `inbox_autoassign`, entre otras).

Ambas tablas ya son creadas idempotentemente por `create_all` en el boot
de la app, por lo que esta migracion es segura de ejecutar en entornos
existentes: `op.create_table` con nombre repetido sobre una tabla ya
presente fallaria, asi que usamos checks contra `inspector` antes de
crear. El `downgrade` si dropea explicitamente.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table_online(table_name: str) -> bool:
    """True si la tabla existe. Solo usar en modo online (conexion viva)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return insp.has_table(table_name)


def _should_create(table_name: str) -> bool:
    """Upgrade: crear salvo que en online la tabla ya exista."""
    from alembic import context

    if context.is_offline_mode():
        return True
    return not _has_table_online(table_name)


def _should_drop(table_name: str) -> bool:
    """Downgrade: dropear salvo que en online la tabla no exista."""
    from alembic import context

    if context.is_offline_mode():
        return True
    return _has_table_online(table_name)


def upgrade() -> None:
    # ── mkt_system_setting ───────────────────────────────────────
    if _should_create("mkt_system_setting"):
        op.create_table(
            "mkt_system_setting",
            sa.Column("key", sa.String(length=100), primary_key=True),
            sa.Column("value", JSONB(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )

    # ── mkt_push_subscription ────────────────────────────────────
    if _should_create("mkt_push_subscription"):
        op.create_table(
            "mkt_push_subscription",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("mkt_user.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("endpoint", sa.Text(), nullable=False),
            sa.Column("p256dh", sa.String(length=255), nullable=False),
            sa.Column("auth", sa.String(length=255), nullable=False),
            sa.Column("user_agent", sa.String(length=500), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("endpoint", name="uq_mkt_push_subscription_endpoint"),
        )
        op.create_index(
            "ix_mkt_push_subscription_user_id",
            "mkt_push_subscription",
            ["user_id"],
        )
        op.create_index(
            "ix_mkt_push_subscription_endpoint",
            "mkt_push_subscription",
            ["endpoint"],
        )


def downgrade() -> None:
    # Intencionalmente NO borramos mkt_system_setting aqui para evitar
    # perder configs guardadas (ai_config, seo_config, inbox_autoassign,
    # etc.). Si se requiere, hacerlo manualmente.
    if _should_drop("mkt_push_subscription"):
        op.drop_index(
            "ix_mkt_push_subscription_endpoint",
            table_name="mkt_push_subscription",
        )
        op.drop_index(
            "ix_mkt_push_subscription_user_id",
            table_name="mkt_push_subscription",
        )
        op.drop_table("mkt_push_subscription")
