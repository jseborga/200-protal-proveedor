"""session_tags (catalogo + junction)

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-23

Fase 5.12 del Conversation Hub: tipificacion de clientes mediante
etiquetas manuales aplicadas a sesiones.

Crea dos tablas:

- `mkt_tag`: catalogo global de etiquetas reutilizables (id, name
  unique, color slug, created_by).
- `mkt_session_tag`: junction entre sesion y tag (session_id, tag_id,
  added_by, added_at). UniqueConstraint (session_id, tag_id).

Ambas son creadas tambien por `Base.metadata.create_all` al boot de la
app, asi que esta migracion chequea existencia via inspector antes de
crear (idempotente online; en offline asume BD virgen como las otras).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table_online(table_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return insp.has_table(table_name)


def _should_create(table_name: str) -> bool:
    from alembic import context

    if context.is_offline_mode():
        return True
    return not _has_table_online(table_name)


def _should_drop(table_name: str) -> bool:
    from alembic import context

    if context.is_offline_mode():
        return True
    return _has_table_online(table_name)


def upgrade() -> None:
    # ── mkt_tag ──────────────────────────────────────────────────
    if _should_create("mkt_tag"):
        op.create_table(
            "mkt_tag",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=60), nullable=False),
            sa.Column(
                "color",
                sa.String(length=20),
                nullable=False,
                server_default="slate",
            ),
            sa.Column(
                "created_by",
                sa.Integer(),
                sa.ForeignKey("mkt_user.id", ondelete="SET NULL"),
                nullable=True,
            ),
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
            sa.UniqueConstraint("name", name="uq_mkt_tag_name"),
        )

    # ── mkt_session_tag ──────────────────────────────────────────
    if _should_create("mkt_session_tag"):
        op.create_table(
            "mkt_session_tag",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "session_id",
                sa.Integer(),
                sa.ForeignKey(
                    "mkt_conversation_session.id", ondelete="CASCADE"
                ),
                nullable=False,
            ),
            sa.Column(
                "tag_id",
                sa.Integer(),
                sa.ForeignKey("mkt_tag.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "added_by",
                sa.Integer(),
                sa.ForeignKey("mkt_user.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "added_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.UniqueConstraint("session_id", "tag_id", name="uq_session_tag"),
        )
        op.create_index(
            "ix_mkt_session_tag_session_id",
            "mkt_session_tag",
            ["session_id"],
        )
        op.create_index(
            "ix_mkt_session_tag_tag_id",
            "mkt_session_tag",
            ["tag_id"],
        )
        op.create_index(
            "ix_session_tag_session_tag",
            "mkt_session_tag",
            ["session_id", "tag_id"],
        )


def downgrade() -> None:
    if _should_drop("mkt_session_tag"):
        op.drop_index(
            "ix_session_tag_session_tag",
            table_name="mkt_session_tag",
        )
        op.drop_index(
            "ix_mkt_session_tag_tag_id",
            table_name="mkt_session_tag",
        )
        op.drop_index(
            "ix_mkt_session_tag_session_id",
            table_name="mkt_session_tag",
        )
        op.drop_table("mkt_session_tag")

    if _should_drop("mkt_tag"):
        op.drop_table("mkt_tag")
