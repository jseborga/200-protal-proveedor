"""last_handoff_at en mkt_conversation_session (Fase 5.10)

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-22

Fase 5.10 agrega la columna `last_handoff_at` (nullable DateTime
timezone-aware) para registrar el timestamp del ultimo auto-handoff
por timeout SLA breach, y asi aplicar un cooldown anti-ping-pong.

Idempotente: chequea si la columna ya existe antes de crearla/dropearla.
En modo offline (`--sql`) genera siempre el DDL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "mkt_conversation_session"
COLUMN = "last_handoff_at"


def _has_column_online(table_name: str, column_name: str) -> bool:
    """True si la columna existe en la tabla. Solo en modo online."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table(table_name):
        return False
    cols = {c["name"] for c in insp.get_columns(table_name)}
    return column_name in cols


def _should_add() -> bool:
    from alembic import context

    if context.is_offline_mode():
        return True
    return not _has_column_online(TABLE, COLUMN)


def _should_drop() -> bool:
    from alembic import context

    if context.is_offline_mode():
        return True
    return _has_column_online(TABLE, COLUMN)


def upgrade() -> None:
    if _should_add():
        op.add_column(
            TABLE,
            sa.Column(
                COLUMN,
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    if _should_drop():
        op.drop_column(TABLE, COLUMN)
