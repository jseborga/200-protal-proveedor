"""Motor de calculo de precios unitarios.

Replica la logica de `apu.item._compute_all_totals` de Odoo
(ssa_construction_apu/models/apu_item.py:939-1011) para que un presupuesto
armado en el portal de el mismo numero al migrarlo al ERP.

Resumen del algoritmo:

    MAT = suma de subtotales de lineas type='mat'
    MO  = suma de subtotales de lineas type='mo'
    EQ  = suma de subtotales de lineas type='eq'

    Las lineas type='sub' (sub-APU) NO suman como bloque: se desagregan en
    los mat/mo/eq de la partida enlazada, multiplicados por el rendimiento.
    Asi los porcentajes de la plantilla (que se aplican sobre MO, sobre el
    costo directo, etc.) siguen cayendo sobre la base correcta.

    costo_directo = MAT + MO + EQ

    Luego se recorre la plantilla en orden de `sequence` acumulando variables:
        sum_mat -> MAT ; sum_mo -> MO ; sum_eq -> EQ
        percent -> eval(formula) * value / 100
        formula -> eval(formula)
    Cada fila deja su resultado en la variable `code`, disponible para las
    siguientes. La fila con `is_total` fija el precio unitario.

    precio_unitario = total de plantilla  o  costo_directo  o  precio_referencia

Las formulas las escriben administradores de empresa, asi que se evaluan con
un interprete de expresiones aritmeticas restringido (`safe_eval_formula`):
solo numeros, variables ya definidas y + - * / ** con parentesis. No hay
llamadas, atributos, indexacion ni acceso a builtins.
"""

from __future__ import annotations

import ast
import operator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# Operadores permitidos en las formulas de plantilla.
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Tope del exponente: evita que `2**999999999` congele el proceso.
_MAX_EXPONENT = 8

# Profundidad maxima de anidamiento de sub-APU.
MAX_SUB_DEPTH = 10


class FormulaError(ValueError):
    """Formula de plantilla invalida o insegura."""


def apu_round(value: float | None, decimals: int = 2) -> float:
    """Redondeo medio-arriba, como `float_round` de Odoo.

    `round()` de Python usa redondeo bancario (round-half-to-even): 10.555
    daria 10.55 y 10.565 daria 10.56. Odoo redondea 0.5 siempre hacia arriba.
    En un presupuesto esa diferencia de centavos se multiplica por cantidades
    y hace que el mismo APU no cuadre entre el portal y el ERP.
    """
    if value is None:
        return 0.0
    try:
        quantum = Decimal(1).scaleb(-decimals)
        return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, OverflowError):
        return 0.0


def safe_eval_formula(expression: str, variables: dict[str, float]) -> float:
    """Evalua una expresion aritmetica contra un diccionario de variables.

    Solo se admite: numeros, nombres definidos en `variables`, los operadores
    + - * / ** y parentesis. Cualquier otra construccion (llamadas, atributos,
    comprensiones, indexacion) se rechaza: estas formulas vienen de la UI.
    """
    if expression is None:
        return 0.0
    expression = str(expression).strip()
    if not expression:
        return 0.0

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Formula invalida: {expression!r}") from exc

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise FormulaError("Solo se admiten numeros en una formula")
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise FormulaError(f"Variable no definida en la plantilla: {node.id}")
            return float(variables[node.id])
        if isinstance(node, ast.BinOp):
            op = _BIN_OPS.get(type(node.op))
            if op is None:
                raise FormulaError("Operador no permitido en una formula")
            left, right = _eval(node.left), _eval(node.right)
            if isinstance(node.op, ast.Pow):
                if abs(right) > _MAX_EXPONENT:
                    raise FormulaError("Exponente fuera de rango")
            if isinstance(node.op, ast.Div) and right == 0:
                return 0.0
            try:
                return float(op(left, right))
            except (OverflowError, ValueError, ZeroDivisionError):
                return 0.0
        if isinstance(node, ast.UnaryOp):
            op = _UNARY_OPS.get(type(node.op))
            if op is None:
                raise FormulaError("Operador unario no permitido")
            return float(op(_eval(node.operand)))
        raise FormulaError("Expresion no permitida en una formula")

    return _eval(tree)


@dataclass
class TemplateLineSpec:
    """Fila de plantilla desacoplada del ORM (facilita test y reuso)."""

    code: str
    name: str
    type: str
    value: float = 0.0
    formula: str | None = None
    is_total: bool = False
    sequence: int = 10


@dataclass
class SummaryRow:
    code: str
    name: str
    line_type: str
    value_formula: str | None
    amount: float
    is_total: bool
    sequence: int


@dataclass
class ItemResult:
    mat_cost: float = 0.0
    mo_cost: float = 0.0
    eq_cost: float = 0.0
    direct_cost: float = 0.0
    unit_price: float = 0.0
    total_price: float = 0.0
    summary: list[SummaryRow] = field(default_factory=list)


def compute_computo_subtotal(pieces, length, width, height, decimals=4) -> float:
    """Cantidad de un computo metrico: piezas x largo x ancho x alto."""
    value = (pieces or 0.0) * (length or 0.0) * (width or 0.0) * (height or 0.0)
    return apu_round(value, decimals)


def compute_line_subtotal(quantity, price_unit, decimals=2) -> float:
    """Subtotal de un componente: rendimiento x precio unitario."""
    return apu_round((quantity or 0.0) * (price_unit or 0.0), decimals)


def apply_template(
    direct: dict[str, float],
    template_lines: list[TemplateLineSpec],
    decimals: int = 2,
) -> tuple[float | None, list[SummaryRow]]:
    """Aplica la plantilla sobre {MAT, MO, EQ}.

    Devuelve (precio_unitario_o_None, filas_de_planilla). None significa que
    la plantilla no declaro ninguna fila `is_total`, en cuyo caso el llamador
    debe caer al costo directo.
    """
    variables: dict[str, float] = {
        "MAT": direct.get("MAT", 0.0),
        "MO": direct.get("MO", 0.0),
        "EQ": direct.get("EQ", 0.0),
    }
    rows: list[SummaryRow] = []
    total: float | None = None

    for line in sorted(template_lines, key=lambda l: (l.sequence, l.code)):
        if line.type == "sum_mat":
            amount = variables["MAT"]
            legend = "Materiales"
        elif line.type == "sum_mo":
            amount = variables["MO"]
            legend = "Mano de obra"
        elif line.type == "sum_eq":
            amount = variables["EQ"]
            legend = "Equipo"
        elif line.type == "percent":
            base = safe_eval_formula(line.formula, variables)
            amount = base * (line.value or 0.0) / 100.0
            legend = f"{line.value}% de ({line.formula})"
        elif line.type == "formula":
            amount = safe_eval_formula(line.formula, variables)
            legend = line.formula
        else:
            raise FormulaError(f"Tipo de linea de plantilla desconocido: {line.type}")

        amount = apu_round(amount, decimals)
        variables[line.code] = amount
        rows.append(
            SummaryRow(
                code=line.code,
                name=line.name,
                line_type=line.type,
                value_formula=legend,
                amount=amount,
                is_total=line.is_total,
                sequence=line.sequence,
            )
        )
        if line.is_total:
            total = amount

    return total, rows


def compute_item(
    lines: list,
    template_lines: list[TemplateLineSpec] | None,
    quantity: float = 1.0,
    reference_price: float | None = None,
    decimals_subtotal: int = 2,
    decimals_total: int = 2,
    sub_costs: dict[int, tuple[float, float, float]] | None = None,
) -> ItemResult:
    """Calcula una partida.

    `lines` son objetos con .type, .quantity, .price_unit y .linked_item_id.
    `sub_costs` mapea id de partida complementaria -> (mat, mo, eq) ya
    calculados, para desagregar las lineas type='sub'.
    """
    sub_costs = sub_costs or {}
    mat = mo = eq = 0.0

    for line in lines:
        subtotal = compute_line_subtotal(
            line.quantity, line.price_unit, decimals_subtotal,
        )
        ltype = line.type
        if ltype == "mat":
            mat += subtotal
        elif ltype == "mo":
            mo += subtotal
        elif ltype == "eq":
            eq += subtotal
        elif ltype == "sub":
            linked = getattr(line, "linked_item_id", None)
            costs = sub_costs.get(linked) if linked else None
            if costs is None:
                # Sub-APU sin partida enlazada (o aun sin calcular): se trata
                # como material, igual que hace Odoo.
                mat += subtotal
            else:
                factor = line.quantity or 0.0
                mat += costs[0] * factor
                mo += costs[1] * factor
                eq += costs[2] * factor

    mat = apu_round(mat, decimals_subtotal)
    mo = apu_round(mo, decimals_subtotal)
    eq = apu_round(eq, decimals_subtotal)
    direct = apu_round(mat + mo + eq, decimals_subtotal)

    unit_price: float | None = None
    summary: list[SummaryRow] = []
    if template_lines:
        unit_price, summary = apply_template(
            {"MAT": mat, "MO": mo, "EQ": eq}, template_lines, decimals_total,
        )

    # Cascada de respaldo identica a Odoo.
    if not unit_price:
        unit_price = direct or (reference_price or 0.0)

    unit_price = apu_round(unit_price, decimals_total)
    total_price = apu_round(unit_price * (quantity or 0.0), decimals_total)

    return ItemResult(
        mat_cost=mat,
        mo_cost=mo,
        eq_cost=eq,
        direct_cost=direct,
        unit_price=unit_price,
        total_price=total_price,
        summary=summary,
    )


# Variables que el motor define antes de evaluar la primera fila.
BUILTIN_VARS = ("MAT", "MO", "EQ")

# Un `code` se usa como nombre de variable en las formulas: debe ser un
# identificador simple, no cualquier texto.
_CODE_RE = __import__("re").compile(r"^[A-Za-z][A-Za-z0-9_]{0,19}$")


def validate_template_lines(lines: list[TemplateLineSpec]) -> list[str]:
    """Comprueba que una plantilla sea evaluable ANTES de guardarla.

    Una plantilla rota no falla al guardarse sino al recalcular, y para
    entonces ya rompio el presupuesto entero. Devuelve la lista de errores
    (vacia si esta bien).

    Se valida:
    * que los codigos sean identificadores validos y no se repitan;
    * que no pisen MAT/MO/EQ, que las define el motor;
    * que las formulas solo referencien variables ya definidas ANTES en el
      orden de evaluacion (una referencia hacia adelante seria None);
    * que las formulas sean aritmetica segura (mismo interprete del motor);
    * que haya como mucho una fila marcada como total.
    """
    errores: list[str] = []
    ordenadas = sorted(lines, key=lambda l: (l.sequence, l.code))

    disponibles = set(BUILTIN_VARS)
    vistos: set[str] = set()
    totales = 0

    for line in ordenadas:
        code = (line.code or "").strip()

        if not _CODE_RE.match(code):
            errores.append(
                f"Codigo invalido: {code!r}. Use letras, numeros y guion bajo, "
                f"empezando por letra (max 20)."
            )
            continue
        if code in BUILTIN_VARS and line.type not in (
            "sum_mat", "sum_mo", "sum_eq",
        ):
            errores.append(
                f"{code} esta reservado para el total de "
                f"{'materiales' if code == 'MAT' else 'mano de obra' if code == 'MO' else 'equipo'}."
            )
            continue
        if code in vistos:
            errores.append(f"El codigo {code} esta repetido en la plantilla.")
            continue
        vistos.add(code)

        if line.type not in ("sum_mat", "sum_mo", "sum_eq", "percent", "formula"):
            errores.append(f"Tipo de fila invalido en {code}: {line.type!r}")
            continue

        if line.type in ("percent", "formula"):
            formula = (line.formula or "").strip()
            if not formula:
                errores.append(
                    f"La fila {code} es de tipo {line.type} y necesita una formula."
                )
            else:
                try:
                    # Se evalua con todas las variables disponibles en 1.0: si
                    # referencia algo aun no definido, levanta aca y no en
                    # produccion.
                    safe_eval_formula(formula, {v: 1.0 for v in disponibles})
                except FormulaError as exc:
                    errores.append(f"Formula de {code}: {exc}")

        if line.type == "percent" and (line.value is None):
            errores.append(f"La fila {code} necesita un porcentaje.")

        if line.is_total:
            totales += 1

        disponibles.add(code)

    if totales > 1:
        errores.append(
            "Solo una fila puede marcarse como precio unitario final."
        )
    return errores


def order_items_for_computation(items: list) -> list:
    """Ordena las partidas para que las complementarias se calculen primero.

    Una partida puede consumir otra via linea type='sub'; hay que resolver la
    dependencia antes. Se hace un orden topologico con deteccion de ciclos:
    si A depende de B y B de A, se rompe el ciclo dejando el resto calculable
    en vez de reventar (un ciclo es un error de captura del usuario, no debe
    tumbar el presupuesto entero).
    """
    by_id = {it.id: it for it in items}
    deps: dict[int, set[int]] = {}
    for it in items:
        linked = set()
        for line in getattr(it, "lines", []) or []:
            if line.type == "sub" and line.linked_item_id in by_id:
                linked.add(line.linked_item_id)
        linked.discard(it.id)  # autorreferencia: se ignora
        deps[it.id] = linked

    ordered: list = []
    visited: dict[int, int] = {}  # 0 = en proceso, 1 = listo

    def visit(item_id: int, depth: int) -> None:
        state = visited.get(item_id)
        if state == 1 or depth > MAX_SUB_DEPTH:
            return
        if state == 0:
            return  # ciclo: se corta aqui
        visited[item_id] = 0
        for dep in deps.get(item_id, ()):
            visit(dep, depth + 1)
        visited[item_id] = 1
        ordered.append(by_id[item_id])

    for it in items:
        visit(it.id, 0)
    return ordered


def detect_cycles(items: list) -> list[int]:
    """Ids de partidas que participan en un ciclo de sub-APU (para avisar)."""
    by_id = {it.id: it for it in items}
    deps: dict[int, set[int]] = {}
    for it in items:
        deps[it.id] = {
            line.linked_item_id
            for line in (getattr(it, "lines", []) or [])
            if line.type == "sub" and line.linked_item_id in by_id
            and line.linked_item_id != it.id
        }

    in_cycle: set[int] = set()
    state: dict[int, int] = {}
    stack: list[int] = []

    def visit(node: int) -> None:
        state[node] = 0
        stack.append(node)
        for dep in deps.get(node, ()):
            if state.get(dep) is None:
                visit(dep)
            elif state.get(dep) == 0:
                # arista hacia atras: todo lo que queda en la pila es ciclo
                if dep in stack:
                    in_cycle.update(stack[stack.index(dep):])
        state[node] = 1
        stack.pop()

    for it in items:
        if state.get(it.id) is None:
            visit(it.id)
    return sorted(in_cycle)
