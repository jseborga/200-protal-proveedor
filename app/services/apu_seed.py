"""Plantillas de calculo por defecto.

Se siembran como plantillas GLOBALES (company_id nulo). Cualquier empresa las
ve y las puede clonar para ajustar sus porcentajes sin tocar la original.

La estructura replica la planilla boliviana habitual (GAMLP): las cargas
sociales se aplican sobre la mano de obra, el IVA sobre mano de obra + cargas,
y luego gastos generales, utilidad e IT se encadenan sobre el acumulado. Es la
misma secuencia de variables que evalua Odoo, para que el numero coincida.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# (code, name, type, value, formula, is_total)
_GAMLP_LINES = [
    ("MAT", "Materiales", "sum_mat", 0.0, None, False),
    ("MO", "Mano de obra", "sum_mo", 0.0, None, False),
    ("EQ", "Equipo, herramientas y maquinaria", "sum_eq", 0.0, None, False),
    ("B1", "Cargas sociales (% de mano de obra)", "percent", 71.18, "MO", False),
    ("B2", "IVA sobre mano de obra", "percent", 14.94, "MO + B1", False),
    ("C", "Costo directo", "formula", 0.0, "MAT + MO + EQ + B1 + B2", False),
    ("D", "Gastos generales y administrativos", "percent", 10.0, "C", False),
    ("E", "Utilidad", "percent", 10.0, "C + D", False),
    ("F", "Impuesto a las transacciones (IT)", "percent", 3.09, "C + D + E", False),
    ("TOTAL", "Precio unitario", "formula", 0.0, "C + D + E + F", True),
]

# Plantilla minima para quien no quiere indirectos: P.U. = costo directo.
_SIMPLE_LINES = [
    ("MAT", "Materiales", "sum_mat", 0.0, None, False),
    ("MO", "Mano de obra", "sum_mo", 0.0, None, False),
    ("EQ", "Equipo", "sum_eq", 0.0, None, False),
    ("TOTAL", "Precio unitario (costo directo)", "formula", 0.0, "MAT + MO + EQ", True),
]

_TEMPLATES = [
    (
        "Boliviana estandar (GAMLP)",
        "Cargas sociales, IVA sobre mano de obra, gastos generales, utilidad e IT. "
        "Es la estructura mas usada en licitaciones publicas en Bolivia.",
        _GAMLP_LINES,
    ),
    (
        "Simple (solo costo directo)",
        "Sin indirectos: el precio unitario es la suma de materiales, mano de "
        "obra y equipo. Util para presupuestos internos rapidos.",
        _SIMPLE_LINES,
    ),
]


async def seed_apu_templates(db: AsyncSession) -> int:
    """Crea las plantillas globales si aun no existen. Idempotente."""
    from app.models.apu import ApuTemplate, ApuTemplateLine

    created = 0
    for name, description, lines in _TEMPLATES:
        exists = (await db.execute(
            select(func.count(ApuTemplate.id)).where(
                ApuTemplate.company_id.is_(None), ApuTemplate.name == name,
            )
        )).scalar() or 0
        if exists:
            continue

        template = ApuTemplate(company_id=None, name=name, description=description)
        db.add(template)
        await db.flush()
        for seq, (code, line_name, ltype, value, formula, is_total) in enumerate(lines, 1):
            db.add(ApuTemplateLine(
                template_id=template.id,
                sequence=seq * 10,
                code=code,
                name=line_name,
                type=ltype,
                value=value,
                formula=formula,
                is_total=is_total,
            ))
        created += 1

    if created:
        await db.commit()
    return created
