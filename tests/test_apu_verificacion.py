"""Verificacion del motor contra un calculo independiente en Decimal.

No se trata de volver a probar lo que ya prueban los otros tests, sino de
contrastar el motor con una implementacion ESCRITA APARTE, con aritmetica
decimal exacta y a mano. Si ambas coinciden sobre casos realistas, el
resultado no depende de un error compartido entre implementacion y test.
"""
from decimal import Decimal, ROUND_HALF_UP

import pytest

from app.services.apu_engine import (
    TemplateLineSpec, apply_template, compute_item,
)


def R(valor, decimales=2) -> Decimal:
    """Redondeo medio-arriba con decimales exactos."""
    q = Decimal(1).scaleb(-decimales)
    return Decimal(str(valor)).quantize(q, rounding=ROUND_HALF_UP)


class _L:
    def __init__(self, tipo, cantidad, precio, linked=None):
        self.type = tipo
        self.quantity = cantidad
        self.price_unit = precio
        self.linked_item_id = linked


# ── Caso 1: APU real de mamposteria, calculado a mano ──────────
def test_muro_de_ladrillo_coincide_con_el_calculo_a_mano():
    """Partida tipica boliviana, con la planilla GAMLP completa.

    Los numeros se calculan aca con Decimal, paso a paso, sin usar el motor.
    """
    # Composicion (rendimiento por m2 de muro)
    materiales = [
        (Decimal("0.0250"), Decimal("57.60")),   # cemento, bls
        (Decimal("0.0900"), Decimal("120.00")),  # arena, m3
        (Decimal("55.0000"), Decimal("1.85")),   # ladrillo, pza
    ]
    mano_obra = [
        (Decimal("1.2000"), Decimal("18.75")),   # albanil, hr
        (Decimal("1.2000"), Decimal("12.50")),   # ayudante, hr
    ]
    equipo = [
        (Decimal("0.0500"), Decimal("35.00")),   # mezcladora, hr
    ]

    MAT = sum((R(q * p) for q, p in materiales), Decimal("0"))
    MO = sum((R(q * p) for q, p in mano_obra), Decimal("0"))
    EQ = sum((R(q * p) for q, p in equipo), Decimal("0"))

    # 1.44 + 10.80 + 101.75
    assert MAT == Decimal("113.99")
    # 22.50 + 15.00
    assert MO == Decimal("37.50")
    assert EQ == Decimal("1.75")

    # Planilla: cargas sociales, IVA sobre MO, GG, utilidad, IT
    B1 = R(MO * Decimal("71.18") / 100)                 # 26.69
    B2 = R((MO + B1) * Decimal("14.94") / 100)          # 9.59
    C = R(MAT + MO + EQ + B1 + B2)                      # 189.52
    D = R(C * Decimal("10.0") / 100)                    # 18.95
    E = R((C + D) * Decimal("10.0") / 100)              # 20.85
    F = R((C + D + E) * Decimal("3.09") / 100)          # 7.08
    PU = R(C + D + E + F)                               # 236.40

    plantilla = [
        TemplateLineSpec("MAT", "Materiales", "sum_mat", sequence=10),
        TemplateLineSpec("MO", "Mano de obra", "sum_mo", sequence=20),
        TemplateLineSpec("EQ", "Equipo", "sum_eq", sequence=30),
        TemplateLineSpec("B1", "Cargas", "percent", 71.18, "MO", sequence=40),
        TemplateLineSpec("B2", "IVA MO", "percent", 14.94, "MO + B1", sequence=50),
        TemplateLineSpec("C", "Costo directo", "formula",
                         formula="MAT + MO + EQ + B1 + B2", sequence=60),
        TemplateLineSpec("D", "Gastos grales", "percent", 10.0, "C", sequence=70),
        TemplateLineSpec("E", "Utilidad", "percent", 10.0, "C + D", sequence=80),
        TemplateLineSpec("F", "IT", "percent", 3.09, "C + D + E", sequence=90),
        TemplateLineSpec("T", "P.U.", "formula", formula="C + D + E + F",
                         is_total=True, sequence=100),
    ]

    lineas = (
        [_L("mat", float(q), float(p)) for q, p in materiales]
        + [_L("mo", float(q), float(p)) for q, p in mano_obra]
        + [_L("eq", float(q), float(p)) for q, p in equipo]
    )
    res = compute_item(lineas, plantilla, quantity=1.0)

    assert Decimal(str(res.mat_cost)) == MAT
    assert Decimal(str(res.mo_cost)) == MO
    assert Decimal(str(res.eq_cost)) == EQ
    assert Decimal(str(res.direct_cost)) == R(MAT + MO + EQ)

    por_codigo = {r.code: Decimal(str(r.amount)) for r in res.summary}
    assert por_codigo["B1"] == B1
    assert por_codigo["B2"] == B2
    assert por_codigo["C"] == C
    assert por_codigo["D"] == D
    assert por_codigo["E"] == E
    assert por_codigo["F"] == F
    assert Decimal(str(res.unit_price)) == PU


def test_el_total_de_la_partida_es_el_pu_por_la_cantidad():
    """Con 125.75 m2 de muro, el total no puede arrastrar error."""
    lineas = [_L("mat", 1.0, 100.0)]
    plantilla = [
        TemplateLineSpec("MAT", "Mat", "sum_mat", sequence=10),
        TemplateLineSpec("T", "PU", "formula", formula="MAT * 1.5",
                         is_total=True, sequence=20),
    ]
    res = compute_item(lineas, plantilla, quantity=125.75)

    PU = R(Decimal("100.00") * Decimal("1.5"))
    assert Decimal(str(res.unit_price)) == PU
    assert Decimal(str(res.total_price)) == R(PU * Decimal("125.75"))


# ── Caso 2: sub-APU, donde es facil equivocarse ────────────────
def test_sub_apu_se_desagrega_y_las_cargas_caen_donde_corresponde():
    """Un mortero usado dentro de un muro.

    La trampa: si el sub-APU se sumara como material, las cargas sociales
    (que van sobre mano de obra) darian de menos. Se verifica con el numero
    exacto de ambas formas.
    """
    # El mortero cuesta, por m3: 200 en materiales, 80 en mano de obra
    mortero = (Decimal("200.00"), Decimal("80.00"), Decimal("0.00"))
    rendimiento = Decimal("0.025")  # m3 de mortero por m2 de muro

    MAT = R(mortero[0] * rendimiento)   # 5.00
    MO = R(mortero[1] * rendimiento)    # 2.00
    B1 = R(MO * Decimal("71.18") / 100)  # 1.42
    PU_correcto = R(MAT + MO + B1)       # 8.42

    plantilla = [
        TemplateLineSpec("MAT", "Mat", "sum_mat", sequence=10),
        TemplateLineSpec("MO", "MO", "sum_mo", sequence=20),
        TemplateLineSpec("EQ", "EQ", "sum_eq", sequence=30),
        TemplateLineSpec("B1", "Cargas", "percent", 71.18, "MO", sequence=40),
        TemplateLineSpec("T", "PU", "formula", formula="MAT + MO + EQ + B1",
                         is_total=True, sequence=50),
    ]
    res = compute_item(
        [_L("sub", float(rendimiento), 0.0, linked=7)],
        plantilla,
        sub_costs={7: (float(mortero[0]), float(mortero[1]), float(mortero[2]))},
    )

    assert Decimal(str(res.mat_cost)) == MAT
    assert Decimal(str(res.mo_cost)) == MO
    assert Decimal(str(res.unit_price)) == PU_correcto

    # Si todo hubiera caido en materiales, faltarian las cargas sociales
    mal = compute_item(
        [_L("sub", float(rendimiento), 0.0, linked=8)],
        plantilla,
        sub_costs={8: (float(mortero[0] + mortero[1]), 0.0, 0.0)},
    )
    assert Decimal(str(mal.unit_price)) == R(MAT + MO)
    assert res.unit_price > mal.unit_price


# ── Caso 3: acumulacion, donde el redondeo podria derivar ──────
@pytest.mark.parametrize("n_lineas", [10, 100, 500])
def test_muchas_lineas_no_acumulan_error(n_lineas):
    """Cada subtotal se redondea; la suma debe seguir siendo exacta."""
    q, p = Decimal("0.125"), Decimal("57.60")
    esperado = R(R(q * p) * n_lineas)

    res = compute_item([_L("mat", float(q), float(p))] * n_lineas, None)
    assert Decimal(str(res.mat_cost)) == esperado


def test_precios_con_tercer_decimal_no_se_pierden_en_el_camino():
    """Un precio de 8.115 debe redondear hacia arriba, no hacia abajo."""
    res = compute_item([_L("mat", 3.0, 8.115)], None)
    assert Decimal(str(res.mat_cost)) == Decimal("24.35")  # no 24.34


# ── Caso 4: la planilla encadena bien las variables ────────────
def test_cada_fila_ve_el_resultado_de_las_anteriores():
    """Verificacion paso a paso del acumulado de variables."""
    plantilla = [
        TemplateLineSpec("MAT", "Mat", "sum_mat", sequence=10),
        TemplateLineSpec("A", "Doble de MAT", "formula", formula="MAT * 2", sequence=20),
        TemplateLineSpec("B", "10% de A", "percent", 10.0, "A", sequence=30),
        TemplateLineSpec("C", "A + B", "formula", formula="A + B",
                         is_total=True, sequence=40),
    ]
    total, filas = apply_template({"MAT": 100.0, "MO": 0.0, "EQ": 0.0}, plantilla)
    v = {f.code: Decimal(str(f.amount)) for f in filas}

    assert v["A"] == Decimal("200.00")
    assert v["B"] == Decimal("20.00")
    assert v["C"] == Decimal("220.00")
    assert Decimal(str(total)) == Decimal("220.00")
