"""APU/presupuestos, biblioteca por empresa y curacion de precios

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-03

Pone Alembic al dia con el modulo de precios unitarios. Hasta ahora estas
tablas solo existian porque `Base.metadata.create_all` las crea al arrancar
la app; sin migracion no habia historial ni forma de volver atras.

Crea:
  mkt_apu_template / mkt_apu_template_line   plantillas de calculo
  mkt_apu_project / mkt_apu_rubro            obra y capitulos
  mkt_apu_item / mkt_apu_line                partida y sus componentes
  mkt_apu_computo / mkt_apu_item_summary     computos y planilla resuelta
  mkt_company_insumo                         biblioteca propia de la empresa
  mkt_price_suggestion                       cola de curacion

Agrega columnas a tablas existentes (planes, suscripciones, empresas) y
CORRIGE un dato: las suscripciones creadas antes de que existiera
`max_projects` quedaron con el default 1, lo que dejaria a una empresa de
plan pago limitada a un solo presupuesto. Se les reponen los limites de su
plan.

Idempotente: comprueba existencia antes de crear, igual que las anteriores,
porque en los entornos ya desplegados `create_all` se adelanto.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLAS_NUEVAS = [
    "mkt_apu_template", "mkt_apu_template_line", "mkt_apu_project",
    "mkt_apu_rubro", "mkt_apu_item", "mkt_apu_line", "mkt_apu_computo",
    "mkt_apu_item_summary", "mkt_company_insumo", "mkt_price_suggestion",
]

# (tabla, columna, tipo SQL, default)
COLUMNAS_NUEVAS = [
    ("mkt_plan", "max_projects", "INTEGER", "1"),
    ("mkt_plan", "trial_days", "INTEGER", "0"),
    ("mkt_plan", "grace_days", "INTEGER", "7"),
    ("mkt_plan", "billing_months", "INTEGER", "1"),
    ("mkt_subscription", "max_projects", "INTEGER", "1"),
    ("mkt_subscription", "grace_days", "INTEGER", "7"),
    ("mkt_subscription", "discount_pct", "DOUBLE PRECISION", "0"),
    ("mkt_company", "contributes_prices", "BOOLEAN", "TRUE"),
]

# Restricciones CHECK sobre los campos que son enumeraciones. La aplicacion
# ya valida, pero una carga masiva o un script de mantenimiento puede meter
# un valor invalido y nadie se entera hasta que rompe un calculo.
CHECKS = [
    ("mkt_apu_line", "ck_apu_line_type", "type IN ('mat','mo','eq','sub')"),
    ("mkt_company_insumo", "ck_company_insumo_type",
     "type IN ('mat','mo','eq','sub')"),
    ("mkt_company_insumo", "ck_company_insumo_source",
     "source_type IN ('manual','catalog')"),
    ("mkt_apu_template_line", "ck_apu_template_line_type",
     "type IN ('sum_mat','sum_mo','sum_eq','percent','formula')"),
    ("mkt_apu_project", "ck_apu_project_state",
     "state IN ('draft','active','closed')"),
    ("mkt_price_suggestion", "ck_price_suggestion_state",
     "state IN ('pending','auto_accepted','accepted','rejected')"),
    ("mkt_price_suggestion", "ck_price_suggestion_kind",
     "kind IN ('price_update','new_insumo')"),
]


def _tablas_existentes(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    existentes = _tablas_existentes(bind)

    # 1. Tablas. En los despliegues actuales `create_all` ya las creo; esta
    #    migracion solo las materializa donde falten (BD virgen, offline).
    faltantes = [t for t in TABLAS_NUEVAS if t not in existentes]
    if faltantes:
        from app.models.base import Base
        import app.models  # noqa: F401  registra el metadata completo

        Base.metadata.create_all(
            bind=bind,
            tables=[Base.metadata.tables[t] for t in faltantes],
        )

    # 2. Columnas agregadas a tablas preexistentes.
    for tabla, columna, tipo, default in COLUMNAS_NUEVAS:
        op.execute(
            f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS "
            f"{columna} {tipo} NOT NULL DEFAULT {default}"
        )
    for tabla, columna, tipo in [
        ("mkt_subscription", "trial_ends_at", "TIMESTAMPTZ"),
        ("mkt_subscription", "discount_note", "VARCHAR(200)"),
        ("mkt_subscription", "discount_until", "DATE"),
        ("mkt_apu_template", "project_id", "INTEGER"),
    ]:
        op.execute(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {columna} {tipo}")

    # 3. Reparacion de datos: las suscripciones anteriores a max_projects
    #    quedaron en 1. Una empresa de plan pago no puede quedar limitada a un
    #    solo presupuesto por un default de columna.
    op.execute("""
        UPDATE mkt_subscription s
           SET max_projects = p.max_projects,
               grace_days   = p.grace_days
          FROM mkt_plan p
         WHERE p.key = s.plan
           AND s.max_projects = 1
           AND p.max_projects > 1
    """)

    # 4. CHECKs. Se agregan como NOT VALID para no bloquear la tabla
    #    validando filas historicas, y se validan despues: si hubiera datos
    #    sucios preexistentes, falla la validacion y no el ALTER.
    for tabla, nombre, condicion in CHECKS:
        if tabla in existentes or tabla in TABLAS_NUEVAS:
            op.execute(f"""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = '{nombre}'
                    ) THEN
                        ALTER TABLE {tabla}
                          ADD CONSTRAINT {nombre} CHECK ({condicion}) NOT VALID;
                    END IF;
                END $$;
            """)
            op.execute(f"ALTER TABLE {tabla} VALIDATE CONSTRAINT {nombre}")


def downgrade() -> None:
    for tabla, nombre, _ in CHECKS:
        op.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS {nombre}")

    for tabla in reversed(TABLAS_NUEVAS):
        op.execute(f"DROP TABLE IF EXISTS {tabla} CASCADE")

    for tabla, columna, _, _ in COLUMNAS_NUEVAS:
        op.execute(f"ALTER TABLE {tabla} DROP COLUMN IF EXISTS {columna}")
    for tabla, columna in [
        ("mkt_subscription", "trial_ends_at"),
        ("mkt_subscription", "discount_note"),
        ("mkt_subscription", "discount_until"),
        ("mkt_apu_template", "project_id"),
    ]:
        op.execute(f"ALTER TABLE {tabla} DROP COLUMN IF EXISTS {columna}")
