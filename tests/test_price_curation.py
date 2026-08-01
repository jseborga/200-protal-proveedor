"""Tests de la compuerta estadistica de curacion de precios.

Es lo que separa un aporte util de un error de tipeo. Si esto falla, el
catalogo publico se degrada solo, asi que se prueban tanto los casos que
deben entrar como los que deben frenarse.
"""
import pytest

from app.services.price_curation import DEFAULTS, evaluate


def _cfg(**over):
    return {**DEFAULTS, **over}


# ── Datos insuficientes ────────────────────────────────────────
def test_sin_historico_va_a_revision():
    """Sin datos previos no hay forma de juzgar: decide un humano."""
    v = evaluate(100.0, [])
    assert v.auto_accept is False
    assert v.state == "pending"
    assert v.sample_count == 0


def test_con_menos_del_minimo_va_a_revision():
    v = evaluate(100.0, [98.0, 102.0], _cfg(min_samples=3))
    assert v.auto_accept is False
    assert "se necesitan 3" in v.reason


def test_justo_en_el_minimo_ya_se_puede_decidir():
    v = evaluate(100.0, [99.0, 100.0, 101.0], _cfg(min_samples=3))
    assert v.sample_count == 3
    assert v.auto_accept is True


# ── Precio coherente: entra solo ───────────────────────────────
def test_precio_dentro_de_la_variacion_normal_entra_solo():
    """El caso feliz: alguien cotizo y el numero es coherente."""
    historico = [57.0, 58.0, 57.5, 59.0, 58.5]
    v = evaluate(58.0, historico)
    assert v.auto_accept is True
    assert v.state == "auto_accepted"
    assert v.z_score is not None and v.z_score < 2.0


def test_variacion_moderada_sigue_entrando():
    historico = [50.0, 55.0, 60.0, 52.0, 58.0]
    v = evaluate(62.0, historico)
    assert v.auto_accept is True


# ── Precio sospechoso: revision humana ─────────────────────────
def test_precio_muy_desviado_va_a_revision():
    """Puede ser un cambio real de mercado, pero lo mira un humano."""
    historico = [57.0, 58.0, 57.5, 59.0, 58.5]
    v = evaluate(85.0, historico)
    assert v.auto_accept is False
    assert v.state == "pending"
    assert v.z_score > 2.0
    assert "supera el umbral" in v.reason


def test_error_de_tipeo_por_orden_de_magnitud_se_marca():
    """5760 en vez de 57.60: no debe entrar solo aunque haya dispersion."""
    historico = [57.0, 58.0, 57.5, 59.0, 58.5]
    v = evaluate(5760.0, historico)
    assert v.auto_accept is False
    assert "error de tipeo" in v.reason


def test_orden_de_magnitud_hacia_abajo_tambien_se_marca():
    historico = [57.0, 58.0, 57.5, 59.0, 58.5]
    v = evaluate(0.58, historico)
    assert v.auto_accept is False
    assert "error de tipeo" in v.reason


def test_la_guardia_de_magnitud_manda_sobre_una_dispersion_enorme():
    """Con historico muy disperso, z podria ser bajo; el ratio lo frena."""
    historico = [10.0, 500.0, 1000.0, 20.0, 800.0]
    v = evaluate(50000.0, historico)
    assert v.auto_accept is False
    assert "error de tipeo" in v.reason


# ── Precios invalidos ──────────────────────────────────────────
@pytest.mark.parametrize("precio", [0.0, -5.0, None])
def test_precio_no_positivo_se_rechaza(precio):
    v = evaluate(precio, [57.0, 58.0, 59.0])
    assert v.state == "rejected"
    assert v.auto_accept is False


# ── Historico sin dispersion ───────────────────────────────────
def test_sin_dispersion_una_variacion_chica_entra():
    """Todos cotizaron 57.60; proponer 60 es plausible."""
    v = evaluate(60.0, [57.6, 57.6, 57.6, 57.6], _cfg(pct_auto=10.0))
    assert v.auto_accept is True
    assert v.stdev == 0.0


def test_sin_dispersion_una_variacion_grande_va_a_revision():
    v = evaluate(75.0, [57.6, 57.6, 57.6, 57.6], _cfg(pct_auto=10.0))
    assert v.auto_accept is False
    assert "supera el" in v.reason


# ── Configuracion ──────────────────────────────────────────────
def test_el_umbral_es_configurable():
    historico = [57.0, 58.0, 57.5, 59.0, 58.5]
    estricto = evaluate(61.0, historico, _cfg(z_auto=1.0))
    permisivo = evaluate(61.0, historico, _cfg(z_auto=5.0))
    assert estricto.auto_accept is False
    assert permisivo.auto_accept is True


def test_se_puede_desactivar_la_aceptacion_automatica():
    """Interruptor para exigir revision humana de todo."""
    v = evaluate(58.0, [57.0, 58.0, 57.5, 59.0], _cfg(auto_accept_enabled=False))
    assert v.auto_accept is False
    assert v.state == "pending"
    assert "desactivada" in v.reason


# ── Datos que informa el veredicto ─────────────────────────────
def test_el_veredicto_explica_la_decision():
    """El curador tiene que poder entender por que llego a su cola."""
    v = evaluate(85.0, [57.0, 58.0, 57.5, 59.0, 58.5])
    assert v.mean == pytest.approx(58.0, abs=0.5)
    assert v.stdev > 0
    assert v.sample_count == 5
    assert v.deviation_pct > 0
    assert len(v.reason) > 20


def test_la_desviacion_porcentual_lleva_signo():
    """Sirve para mostrar si el precio subio o bajo."""
    sube = evaluate(70.0, [57.0, 58.0, 57.5, 59.0, 58.5])
    baja = evaluate(45.0, [57.0, 58.0, 57.5, 59.0, 58.5])
    assert sube.deviation_pct > 0
    assert baja.deviation_pct < 0


def test_se_ignoran_las_observaciones_invalidas():
    """Ceros y negativos del historico no deben torcer la media."""
    v = evaluate(58.0, [57.0, 0.0, 58.0, -3.0, 59.0])
    assert v.sample_count == 3
    assert v.mean == pytest.approx(58.0, abs=0.1)
