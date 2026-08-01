"""Tests del motor de calculo de precios unitarios.

Verifican dos cosas distintas:
1. Que el resultado numerico coincide con la logica de Odoo (para que un
   presupuesto migre sin cambiar de valor).
2. Que el evaluador de formulas no permite ejecutar nada peligroso: las
   formulas las escriben usuarios desde la UI.
"""
import pytest

from app.services.apu_engine import (
    FormulaError,
    TemplateLineSpec,
    apply_template,
    compute_computo_subtotal,
    compute_item,
    compute_line_subtotal,
    detect_cycles,
    order_items_for_computation,
    safe_eval_formula,
)


class _Line:
    """Doble de ApuLine para los tests."""

    def __init__(self, type, quantity, price_unit, linked_item_id=None):
        self.type = type
        self.quantity = quantity
        self.price_unit = price_unit
        self.linked_item_id = linked_item_id


class _Item:
    def __init__(self, id, lines):
        self.id = id
        self.lines = lines


# ── Evaluador de formulas: seguridad ───────────────────────────
@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('rm -rf /')",
        "().__class__.__bases__[0].__subclasses__()",
        "open('/etc/passwd').read()",
        "MAT.__class__",
        "[x for x in range(10)]",
        "exec('x=1')",
        "globals()",
        "lambda: 1",
        "MAT if MAT else 0",
    ],
)
def test_formula_rechaza_construcciones_peligrosas(expr):
    """Las formulas vienen de la UI: solo aritmetica sobre variables."""
    with pytest.raises((FormulaError, ValueError)):
        safe_eval_formula(expr, {"MAT": 100.0})


def test_formula_rechaza_variable_no_definida():
    with pytest.raises(FormulaError):
        safe_eval_formula("NO_EXISTE + 1", {"MAT": 10.0})


def test_formula_rechaza_exponente_gigante():
    """Evita congelar el proceso con 2**999999999."""
    with pytest.raises(FormulaError):
        safe_eval_formula("MAT ** 999999999", {"MAT": 10.0})


def test_formula_division_por_cero_no_revienta():
    assert safe_eval_formula("MAT / 0", {"MAT": 10.0}) == 0.0


@pytest.mark.parametrize(
    "expr,esperado",
    [
        ("MAT + MO + EQ", 60.0),
        ("MAT * 2", 20.0),
        ("(MAT + MO) * 2", 60.0),
        ("MAT - MO", -10.0),
        ("MO / MAT", 2.0),
        ("-MAT", -10.0),
        ("MAT ** 2", 100.0),
        ("", 0.0),
    ],
)
def test_formula_aritmetica_valida(expr, esperado):
    assert safe_eval_formula(expr, {"MAT": 10.0, "MO": 20.0, "EQ": 30.0}) == esperado


# ── Calculos base ──────────────────────────────────────────────
def test_subtotal_de_linea_es_rendimiento_por_precio():
    assert compute_line_subtotal(1.5, 10.0) == 15.0
    assert compute_line_subtotal(0.125, 8.0) == 1.0


def test_computo_metrico_multiplica_las_cuatro_dimensiones():
    assert compute_computo_subtotal(2, 3.0, 4.0, 0.5) == 12.0


# ── Plantilla de calculo ───────────────────────────────────────
def _plantilla_gamlp() -> list[TemplateLineSpec]:
    """Estructura tipica boliviana: cargas sociales, IVA, GG, utilidad, IT."""
    return [
        TemplateLineSpec("MAT", "Materiales", "sum_mat", sequence=10),
        TemplateLineSpec("MO", "Mano de obra", "sum_mo", sequence=20),
        TemplateLineSpec("EQ", "Equipo", "sum_eq", sequence=30),
        TemplateLineSpec(
            "B1", "Cargas sociales", "percent", value=71.18, formula="MO", sequence=40,
        ),
        TemplateLineSpec(
            "B2", "IVA mano de obra", "percent", value=14.94,
            formula="MO + B1", sequence=50,
        ),
        TemplateLineSpec(
            "C", "Costo directo", "formula",
            formula="MAT + MO + EQ + B1 + B2", sequence=60,
        ),
        TemplateLineSpec(
            "D", "Gastos generales", "percent", value=10.0, formula="C", sequence=70,
        ),
        TemplateLineSpec(
            "E", "Utilidad", "percent", value=10.0, formula="C + D", sequence=80,
        ),
        TemplateLineSpec(
            "F", "Impuesto IT", "percent", value=3.09, formula="C + D + E", sequence=90,
        ),
        TemplateLineSpec(
            "TOTAL", "Precio unitario", "formula",
            formula="C + D + E + F", is_total=True, sequence=100,
        ),
    ]


def test_plantilla_encadena_variables_en_orden():
    """Cada fila deja su valor disponible para las siguientes."""
    total, rows = apply_template(
        {"MAT": 100.0, "MO": 200.0, "EQ": 50.0}, _plantilla_gamlp(),
    )

    por_codigo = {r.code: r.amount for r in rows}
    assert por_codigo["MAT"] == 100.0
    assert por_codigo["MO"] == 200.0
    assert por_codigo["EQ"] == 50.0
    assert por_codigo["B1"] == round(200.0 * 0.7118, 2)          # 142.36
    assert por_codigo["B2"] == round((200.0 + 142.36) * 0.1494, 2)  # 51.15
    c = round(100.0 + 200.0 + 50.0 + 142.36 + 51.15, 2)          # 543.51
    assert por_codigo["C"] == c
    assert por_codigo["D"] == round(c * 0.10, 2)
    assert total == por_codigo["TOTAL"]
    assert total > c  # los indirectos suman


def test_plantilla_sin_fila_total_devuelve_none():
    total, rows = apply_template(
        {"MAT": 10.0, "MO": 0.0, "EQ": 0.0},
        [TemplateLineSpec("MAT", "Materiales", "sum_mat")],
    )
    assert total is None
    assert len(rows) == 1


def test_plantilla_marca_la_fila_total():
    _, rows = apply_template({"MAT": 1.0, "MO": 1.0, "EQ": 1.0}, _plantilla_gamlp())
    totales = [r for r in rows if r.is_total]
    assert len(totales) == 1
    assert totales[0].code == "TOTAL"


# ── Calculo de partida ─────────────────────────────────────────
def test_partida_agrupa_por_tipo_de_recurso():
    lines = [
        _Line("mat", 2.0, 50.0),    # 100
        _Line("mat", 1.0, 25.0),    # 25
        _Line("mo", 8.0, 12.5),     # 100
        _Line("eq", 0.5, 40.0),     # 20
    ]
    res = compute_item(lines, None)

    assert res.mat_cost == 125.0
    assert res.mo_cost == 100.0
    assert res.eq_cost == 20.0
    assert res.direct_cost == 245.0


def test_sin_plantilla_el_precio_unitario_es_el_costo_directo():
    res = compute_item([_Line("mat", 1.0, 80.0)], None)
    assert res.unit_price == 80.0


def test_sin_lineas_cae_al_precio_de_referencia():
    res = compute_item([], None, reference_price=250.0)
    assert res.unit_price == 250.0


def test_total_es_precio_unitario_por_cantidad():
    res = compute_item([_Line("mat", 1.0, 100.0)], None, quantity=12.0)
    assert res.unit_price == 100.0
    assert res.total_price == 1200.0


def test_sub_apu_se_desagrega_en_mat_mo_eq():
    """Un sub-APU NO debe sumar como material: sus componentes van a su bloque.

    Si cayera todo en MAT, los porcentajes sobre mano de obra (cargas
    sociales) se calcularian mal.
    """
    lines = [
        _Line("mo", 1.0, 100.0),
        _Line("sub", 2.0, 0.0, linked_item_id=7),
    ]
    # La partida 7 cuesta 10 mat + 30 mo + 5 eq por unidad
    res = compute_item(lines, None, sub_costs={7: (10.0, 30.0, 5.0)})

    assert res.mat_cost == 20.0          # 10 * 2
    assert res.mo_cost == 100.0 + 60.0   # propia + 30 * 2
    assert res.eq_cost == 10.0           # 5 * 2
    assert res.direct_cost == 190.0


def test_sub_apu_sin_enlace_se_trata_como_material():
    """Igual que Odoo cuando falta linked_item_id."""
    res = compute_item([_Line("sub", 1.0, 50.0)], None, sub_costs={})
    assert res.mat_cost == 50.0
    assert res.mo_cost == 0.0


def test_sub_apu_afecta_las_cargas_sociales():
    """Comprobacion de que la desagregacion cambia el resultado final."""
    plantilla = [
        TemplateLineSpec("MAT", "Mat", "sum_mat", sequence=10),
        TemplateLineSpec("MO", "MO", "sum_mo", sequence=20),
        TemplateLineSpec("EQ", "EQ", "sum_eq", sequence=30),
        TemplateLineSpec("B1", "Cargas", "percent", value=71.18, formula="MO", sequence=40),
        TemplateLineSpec(
            "T", "Total", "formula", formula="MAT + MO + EQ + B1",
            is_total=True, sequence=50,
        ),
    ]
    linea_sub = [_Line("sub", 1.0, 0.0, linked_item_id=1)]

    como_mo = compute_item(linea_sub, plantilla, sub_costs={1: (0.0, 100.0, 0.0)})
    como_mat = compute_item(linea_sub, plantilla, sub_costs={1: (100.0, 0.0, 0.0)})

    assert como_mo.unit_price == round(100.0 + 71.18, 2)
    assert como_mat.unit_price == 100.0
    assert como_mo.unit_price > como_mat.unit_price


# ── Orden de calculo y ciclos ──────────────────────────────────
def test_las_complementarias_se_calculan_primero():
    base = _Item(1, [])
    usa_base = _Item(2, [_Line("sub", 1.0, 0.0, linked_item_id=1)])
    orden = order_items_for_computation([usa_base, base])
    assert [i.id for i in orden] == [1, 2]


def test_cadena_de_tres_niveles_se_ordena_bien():
    a = _Item(1, [])
    b = _Item(2, [_Line("sub", 1.0, 0.0, linked_item_id=1)])
    c = _Item(3, [_Line("sub", 1.0, 0.0, linked_item_id=2)])
    orden = order_items_for_computation([c, b, a])
    assert [i.id for i in orden] == [1, 2, 3]


def test_ciclo_no_cuelga_el_calculo():
    """Un ciclo es un error de captura: no debe tumbar el presupuesto."""
    a = _Item(1, [_Line("sub", 1.0, 0.0, linked_item_id=2)])
    b = _Item(2, [_Line("sub", 1.0, 0.0, linked_item_id=1)])
    orden = order_items_for_computation([a, b])
    assert len(orden) <= 2  # termina, no hay recursion infinita


def test_se_detectan_las_partidas_en_ciclo():
    a = _Item(1, [_Line("sub", 1.0, 0.0, linked_item_id=2)])
    b = _Item(2, [_Line("sub", 1.0, 0.0, linked_item_id=1)])
    c = _Item(3, [])
    ciclo = detect_cycles([a, b, c])
    assert set(ciclo) == {1, 2}


def test_autorreferencia_no_es_ciclo_ni_cuelga():
    a = _Item(1, [_Line("sub", 1.0, 0.0, linked_item_id=1)])
    assert order_items_for_computation([a])
    assert detect_cycles([a]) == []


# ── Redondeo ───────────────────────────────────────────────────
def test_el_rendimiento_admite_tres_decimales():
    """0.125 bolsas de cemento por m2 es un rendimiento real."""
    res = compute_item([_Line("mat", 0.125, 57.60)], None)
    assert res.mat_cost == 7.20


def test_los_decimales_son_configurables_por_obra():
    lines = [_Line("mat", 1.0, 10.555)]
    assert compute_item(lines, None, decimals_subtotal=2).mat_cost == 10.56
    assert compute_item(lines, None, decimals_subtotal=3).mat_cost == 10.555


# ── Redondeo compatible con Odoo ───────────────────────────────
def test_redondeo_es_medio_arriba_no_bancario():
    """Odoo redondea 0.5 hacia arriba; round() de Python al par mas cercano.

    Sin esto el mismo APU da distinto en el portal y en el ERP.
    """
    from app.services.apu_engine import apu_round

    assert apu_round(10.555, 2) == 10.56   # round() daria 10.55
    assert apu_round(10.565, 2) == 10.57
    assert apu_round(2.5, 0) == 3.0        # round() daria 2
    assert apu_round(3.5, 0) == 4.0
    assert apu_round(-2.5, 0) == -3.0
    assert apu_round(None, 2) == 0.0


def test_el_redondeo_medio_arriba_llega_al_subtotal():
    assert compute_line_subtotal(1.0, 10.555, 2) == 10.56
