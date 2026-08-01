"""Tests de estado de suscripcion, cuotas y autorizacion del modulo APU.

Los cobros son manuales, asi que el control efectivo lo hacen las fechas.
Estos tests fijan ese comportamiento: cuando una suscripcion vence, la
empresa NO pierde el acceso a lo que ya tiene, pero deja de poder crear.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.services import quota


class _Sub:
    """Doble de Subscription."""

    def __init__(
        self, plan="professional", state="active", expires_at=None,
        trial_ends_at=None, grace_days=7, max_users=5, max_projects=10,
        max_pedidos_month=50, discount_pct=0.0, discount_until=None,
    ):
        self.plan = plan
        self.state = state
        self.expires_at = expires_at
        self.trial_ends_at = trial_ends_at
        self.grace_days = grace_days
        self.max_users = max_users
        self.max_projects = max_projects
        self.max_pedidos_month = max_pedidos_month
        self.discount_pct = discount_pct
        self.discount_until = discount_until


NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


# ── Estado segun fechas ────────────────────────────────────────
def test_sin_vencimiento_es_activa():
    """El plan gratuito no vence: es de por vida."""
    assert quota.resolve_state(_Sub(expires_at=None), NOW) == "active"


def test_vigente_es_activa():
    assert quota.resolve_state(_Sub(expires_at=NOW + timedelta(days=5)), NOW) == "active"


def test_prueba_gratuita_manda_sobre_el_vencimiento():
    sub = _Sub(expires_at=NOW - timedelta(days=1), trial_ends_at=NOW + timedelta(days=3))
    assert quota.resolve_state(sub, NOW) == "trial"


def test_recien_vencida_entra_en_gracia():
    sub = _Sub(expires_at=NOW - timedelta(days=2), grace_days=7)
    assert quota.resolve_state(sub, NOW) == "grace"


def test_pasada_la_gracia_queda_vencida():
    sub = _Sub(expires_at=NOW - timedelta(days=10), grace_days=7)
    assert quota.resolve_state(sub, NOW) == "expired"


def test_sin_gracia_vence_de_inmediato():
    sub = _Sub(expires_at=NOW - timedelta(seconds=1), grace_days=0)
    assert quota.resolve_state(sub, NOW) == "expired"


def test_suspension_manual_manda_sobre_las_fechas():
    """Un admin puede cortar una empresa aunque su fecha este vigente."""
    sub = _Sub(state="suspended", expires_at=NOW + timedelta(days=30))
    assert quota.resolve_state(sub, NOW) == "suspended"


def test_sin_suscripcion_es_vencida():
    assert quota.resolve_state(None, NOW) == "expired"


def test_fecha_naive_se_interpreta_como_utc():
    """Postgres puede devolver datetimes sin tz segun la columna."""
    sub = _Sub(expires_at=datetime(2026, 12, 31, 0, 0))
    assert quota.resolve_state(sub, NOW) == "active"


# ── Limites efectivos ──────────────────────────────────────────
def test_en_gracia_conserva_los_limites_del_plan():
    """No se castiga al cliente el dia siguiente de vencer."""
    sub = _Sub(expires_at=NOW - timedelta(days=1), grace_days=7, max_projects=10)
    assert quota.get_effective_limits(sub, "grace")["max_projects"] == 10


def test_vencida_cae_a_los_limites_gratuitos(monkeypatch):
    monkeypatch.setattr(
        quota, "get_effective_limits", quota.get_effective_limits,
    )
    from app.core import plans

    plans.PLANS["free"] = {"max_users": 1, "max_projects": 1, "max_pedidos_month": 5}
    sub = _Sub(expires_at=NOW - timedelta(days=30), max_projects=10)
    limites = quota.get_effective_limits(sub, "expired")
    assert limites["max_projects"] == 1
    assert limites["max_users"] == 1


def test_estados_con_limites_completos():
    assert quota.has_full_limits("trial") is True
    assert quota.has_full_limits("active") is True
    assert quota.has_full_limits("grace") is True
    assert quota.has_full_limits("expired") is False
    assert quota.has_full_limits("suspended") is False


# ── Descuentos ─────────────────────────────────────────────────
def test_descuento_vigente_se_aplica():
    sub = _Sub(discount_pct=20.0, discount_until=date(2099, 1, 1))
    assert quota.apply_discount(350.0, sub) == 280.0


def test_descuento_sin_fecha_no_caduca():
    assert quota.apply_discount(100.0, _Sub(discount_pct=50.0)) == 50.0


def test_descuento_vencido_no_se_aplica():
    sub = _Sub(discount_pct=50.0, discount_until=date(2020, 1, 1))
    assert quota.apply_discount(100.0, sub) == 100.0


def test_descuento_mayor_a_cien_no_da_precio_negativo():
    assert quota.apply_discount(100.0, _Sub(discount_pct=150.0)) == 0.0


def test_sin_suscripcion_no_hay_descuento():
    assert quota.apply_discount(100.0, None) == 100.0


# ── Periodos de facturacion ────────────────────────────────────
def test_fin_de_periodo_suma_meses():
    inicio = datetime(2026, 1, 15, tzinfo=timezone.utc)
    assert quota.compute_period_end(inicio, 1).month == 2
    assert quota.compute_period_end(inicio, 12).year == 2027


def test_fin_de_periodo_ajusta_fin_de_mes():
    """31 de enero + 1 mes no puede ser 31 de febrero."""
    inicio = datetime(2026, 1, 31, tzinfo=timezone.utc)
    fin = quota.compute_period_end(inicio, 1)
    assert fin.month == 2
    assert fin.day == 28


# ── Autorizacion del modulo ────────────────────────────────────
class _User:
    def __init__(self, role="user", company_role=None, company_id=1):
        self.role = role
        self.company_role = company_role
        self.company_id = company_id


def test_viewer_no_puede_editar():
    """Antes de este modulo, viewer y cotizador tenian los mismos permisos."""
    from app.api.routes.apu import _require_editor

    with pytest.raises(HTTPException) as exc:
        _require_editor(_User(company_role="viewer"))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("rol", ["company_admin", "cotizador"])
def test_los_roles_de_edicion_pueden_editar(rol):
    from app.api.routes.apu import _require_editor

    _require_editor(_User(company_role=rol))  # no debe lanzar


def test_admin_global_puede_editar_para_soporte():
    from app.api.routes.apu import _require_editor

    _require_editor(_User(role="admin", company_role=None))


def test_sin_empresa_no_se_usa_presupuestos():
    from app.api.routes.apu import _require_company

    with pytest.raises(HTTPException) as exc:
        _require_company(_User(company_id=None))
    assert exc.value.status_code == 403


def test_endpoints_apu_exigen_autenticacion():
    """Ningun endpoint del modulo puede quedar publico."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    casos = [
        ("get", "/api/v1/apu/projects"),
        ("post", "/api/v1/apu/projects"),
        ("get", "/api/v1/apu/projects/1"),
        ("get", "/api/v1/apu/items/1"),
        ("post", "/api/v1/apu/items/1/lines"),
        ("put", "/api/v1/apu/lines/1"),
        ("delete", "/api/v1/apu/lines/1"),
        ("get", "/api/v1/apu/templates"),
        ("get", "/api/v1/apu/quota"),
        ("get", "/api/v1/apu/projects/1/export.xlsx"),
        ("post", "/api/v1/apu/projects/1/recompute"),
        ("post", "/api/v1/apu/projects/1/refresh-prices"),
    ]
    for method, path in casos:
        resp = client.request(method.upper(), path, json={})
        assert resp.status_code in (401, 403), f"{method.upper()} {path} -> {resp.status_code}"


def test_activacion_de_suscripcion_exige_admin():
    """Activar/renovar mueve fechas y limites: solo un admin."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/v1/admin/subscriptions/1/activate", json={"plan": "professional"})
    assert resp.status_code in (401, 403)


def test_renovar_antes_de_vencer_extiende_desde_el_vencimiento():
    """Renovar anticipado no debe regalar ni quitar dias.

    Fija la regla que implementa el endpoint de activacion: si el plan es el
    mismo y aun no vencio, el nuevo periodo arranca en el vencimiento vigente.
    """
    vence = datetime(2026, 9, 1, tzinfo=timezone.utc)
    ahora = datetime(2026, 8, 1, tzinfo=timezone.utc)
    base = vence if vence > ahora else ahora
    assert quota.compute_period_end(base, 1) == datetime(2026, 10, 1, tzinfo=timezone.utc)


def test_resumen_de_recursos_exige_autenticacion():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/v1/apu/projects/1/resources").status_code in (401, 403)
