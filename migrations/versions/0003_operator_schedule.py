"""mkt_operator_schedule (Fase 5.8)

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-22

Crea la tabla mkt_operator_schedule que almacena ventanas horarias
semanales on-duty por operador (Fase 5.8). Ver app/models/operator_schedule.py
para los detalles del modelo.

Idempotente: chequea si la tabla ya existe antes de crearla (coexiste con
`Base.metadata.create_all` del boot). Offline mode genera DDL completo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "mkt_operator_schedule"


def _has_table_online(table_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return insp.has_table(table_name)


def _should_create() -> bool:
    from alembic import context

    if context.is_offline_mode():
        return True
    return not _has_table_online(TABLE)


def _should_drop() -> bool:
    from alembic import context

    if context.is_offline_mode():
        return True
    return _has_table_online(TABLE)


def upgrade() -> None:
    if _should_create():
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("mkt_user.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("weekday", sa.Integer(), nullable=False),
            sa.Column("start_time", sa.Time(), nullable=False),
            sa.Column("end_time", sa.Time(), nullable=False),
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
            sa.CheckConstraint(
                "weekday BETWEEN 0 AND 6",
                name="ck_mkt_operator_schedule_weekday",
            ),
        )
        op.create_index(
            "ix_mkt_operator_schedule_user_id",
            TABLE,
            ["user_id"],
        )
        op.create_index(
            "ix_mkt_operator_schedule_user_weekday",
            TABLE,
            ["user_id", "weekday"],
        )


def downgrade() -> None:
    if _should_drop():
        op.drop_index(
            "ix_mkt_operator_schedule_user_weekday",
            table_name=TABLE,
        )
        op.drop_index(
            "ix_mkt_operator_schedule_user_id",
            table_name=TABLE,
        )
        op.drop_table(TABLE)
