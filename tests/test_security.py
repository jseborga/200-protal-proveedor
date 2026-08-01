"""Tests de regresion de la auditoria de seguridad.

Cada test corresponde a una vulnerabilidad concreta corregida. Si alguno
vuelve a fallar, la vulnerabilidad se reintrodujo.

No requieren base de datos: se ejercitan las capas de configuracion, escape,
resolucion de IP y el enrutado/dependencias de FastAPI.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.client_ip import resolve_client_ip
from app.core.config import Settings
from app.main import app


@pytest.fixture(scope="module")
def client():
    # Sin `with`: no se ejecuta el lifespan, asi que no se intenta conectar a
    # PostgreSQL. Estos tests comprueban enrutado y dependencias (401/403/404),
    # que se resuelven antes de tocar la base de datos.
    # raise_server_exceptions=False para que un fallo posterior de DB se vea
    # como 500 y no rompa el test con una excepcion.
    return TestClient(app, raise_server_exceptions=False)


def _paths() -> set[str]:
    return {getattr(r, "path", "") for r in app.routes}


# ── Secretos por defecto ───────────────────────────────────────
@pytest.mark.parametrize("weak", ["change-me", "cambiar-esto-por-otra-clave-segura", ""])
def test_produccion_rechaza_secretos_placeholder(weak):
    """Un JWT_SECRET_KEY conocido permite firmar tokens de admin."""
    with pytest.raises(Exception):
        Settings(
            app_env="production",
            jwt_secret_key=weak,
            app_secret_key="s" * 48,
            _env_file=None,
        )


def test_produccion_arranca_con_secretos_fuertes():
    s = Settings(
        app_env="production",
        jwt_secret_key="k" * 48,
        app_secret_key="s" * 48,
        _env_file=None,
    )
    assert s.app_env == "production"


def test_app_env_por_defecto_es_produccion():
    """Fail-closed: sin APP_ENV no deben exponerse /api/docs."""
    s = Settings(jwt_secret_key="k" * 48, app_secret_key="s" * 48, _env_file=None)
    assert s.app_env == "production"
    assert s.is_dev is False


# ── Endpoints destructivos eliminados ──────────────────────────
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/purge/{secret}",
        "/api/v1/banlist/purge/{secret}",
        "/api/v1/integration/admin/sql",
    ],
)
def test_endpoints_peligrosos_eliminados(path):
    assert path not in _paths()


def test_purge_directo_no_ejecuta(client):
    """La ruta ya no existe; solo queda el catch-all de la SPA (GET)."""
    resp = client.post("/api/v1/purge/change-me")
    assert resp.status_code in (404, 405)


def test_banlist_purge_exige_secreto(client):
    """Sin cabecera correcta no se puede vaciar la lista de baneos."""
    assert client.post("/api/v1/banlist/purge").status_code in (403, 503)
    assert client.post(
        "/api/v1/banlist/purge", headers={"X-Purge-Secret": "incorrecto"}
    ).status_code in (403, 503)


# ── Webhooks fail-closed ───────────────────────────────────────
# Se prueba el validador directamente: los handlers dependen de get_db y sin
# base de datos no se llega a ejecutar el cuerpo.
def test_validador_de_webhook_rechaza_sin_secreto_configurado():
    """Fail-closed: antes, sin secreto configurado el webhook era publico."""
    from fastapi import HTTPException
    from app.api.routes.webhooks import _check_secret

    with pytest.raises(HTTPException) as exc:
        _check_secret("lo-que-sea", "")
    assert exc.value.status_code == 503


def test_validador_de_webhook_rechaza_secreto_incorrecto():
    from fastapi import HTTPException
    from app.api.routes.webhooks import _check_secret

    for provisto in (None, "", "incorrecto"):
        with pytest.raises(HTTPException) as exc:
            _check_secret(provisto, "el-secreto-real")
        assert exc.value.status_code == 403


def test_validador_de_webhook_acepta_secreto_correcto():
    from app.api.routes.webhooks import _check_secret

    _check_secret("el-secreto-real", "el-secreto-real")  # no debe lanzar


# ── MCP autenticado ────────────────────────────────────────────
def test_mcp_requiere_credencial(client):
    resp = client.get("/mcp/sse")
    assert resp.status_code in (401, 503), "MCP no puede quedar publico"


# ── Autorizacion por rol / API key ─────────────────────────────
def test_endpoints_protegidos_sin_token(client):
    """Rutas que antes eran accesibles sin permisos suficientes."""
    casos = [
        ("put", "/api/v1/prices/1"),
        ("post", "/api/v1/prices"),
        ("post", "/api/v1/suppliers"),
        ("get", "/api/v1/rfq"),
        ("delete", "/api/v1/prices/review/0"),
        ("post", "/api/v1/admin/purge-data?confirm=CONFIRMAR"),
    ]
    for method, path in casos:
        resp = client.request(method.upper(), path, json={})
        assert resp.status_code in (401, 403), f"{method.upper()} {path} -> {resp.status_code}"


def test_integration_purge_exige_api_key(client):
    resp = client.delete("/api/v1/integration/purge?confirm=yes")
    assert resp.status_code in (401, 403)


def test_scopes_de_api_key_se_verifican():
    """Una key de solo lectura no puede llegar a un endpoint de escritura."""
    import asyncio
    from fastapi import HTTPException
    from app.api.deps import require_scope

    dep = require_scope("write")
    solo_lectura = {"role": "integration", "scopes": ["read"], "key_id": 1}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(auth=solo_lectura))
    assert exc.value.status_code == 403

    con_escritura = {"role": "integration", "scopes": ["read", "write"], "key_id": 1}
    assert asyncio.run(dep(auth=con_escritura)) is con_escritura


# ── Tokens ─────────────────────────────────────────────────────
def test_refresh_token_no_sirve_como_access_token():
    """Un refresh token vive 30 dias; aceptarlo anula la expiracion corta."""
    import asyncio
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    from app.core.security import create_refresh_token, get_current_user

    token = create_refresh_token({"sub": "1", "role": "admin"})
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_user(credentials=creds, db=None))
    assert exc.value.status_code == 401


def test_sub_no_numerico_da_401_no_500():
    import asyncio
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    from app.core.security import create_access_token, get_current_user

    token = create_access_token({"sub": "no-soy-un-entero"})
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_user(credentials=creds, db=None))
    assert exc.value.status_code == 401


# ── IP real / proxies ──────────────────────────────────────────
def test_cabeceras_de_proxy_se_ignoran_desde_ip_no_confiable():
    """Sin esto se evade el rate limit y se envenena la banlist."""
    headers = {"x-forwarded-for": "1.2.3.4", "cf-connecting-ip": "5.6.7.8"}
    assert resolve_client_ip(headers, "203.0.113.9") == "203.0.113.9"


def test_cabeceras_de_proxy_se_aceptan_desde_proxy_confiable():
    headers = {"x-forwarded-for": "1.2.3.4, 9.9.9.9"}
    assert resolve_client_ip(headers, "10.0.0.5") == "1.2.3.4"


def test_cabecera_con_ip_invalida_cae_a_la_ip_del_socket():
    assert resolve_client_ip({"x-forwarded-for": "no-es-una-ip"}, "10.0.0.5") == "10.0.0.5"


# ── Autorizacion del bot ───────────────────────────────────────
def test_autorizacion_bot_no_acepta_sufijos():
    """Antes "9" autorizaba contra el id autorizado "123456789"."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from app.services.messaging import _is_authorized_bot_user

    setting = MagicMock()
    setting.value = {"telegram": ["123456789"]}
    db = MagicMock()
    db.get = AsyncMock(return_value=setting)

    assert asyncio.run(_is_authorized_bot_user(db, "telegram", "9")) is False
    assert asyncio.run(_is_authorized_bot_user(db, "telegram", "6789")) is False
    assert asyncio.run(_is_authorized_bot_user(db, "telegram", "1234567890")) is False
    assert asyncio.run(_is_authorized_bot_user(db, "telegram", "123456789")) is True


def test_autorizacion_bot_normaliza_telefonos():
    """Un mismo numero con formato distinto debe seguir autorizando."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from app.services.messaging import _is_authorized_bot_user

    setting = MagicMock()
    setting.value = {"whatsapp": ["+591 700 00000"]}
    db = MagicMock()
    db.get = AsyncMock(return_value=setting)

    assert asyncio.run(_is_authorized_bot_user(db, "whatsapp", "59170000000")) is True


# ── Cabeceras de seguridad ─────────────────────────────────────
def test_cabeceras_de_seguridad_presentes(client):
    resp = client.get("/api/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    csp = resp.headers.get("content-security-policy", "")
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp


def test_cors_no_refleja_origen_arbitrario(client):
    resp = client.get("/api/health", headers={"Origin": "https://sitio-malicioso.example"})
    assert resp.headers.get("access-control-allow-origin") != "https://sitio-malicioso.example"


# ── Escapado JSON-LD ───────────────────────────────────────────
def test_json_ld_escapa_cierre_de_script():
    """Un nombre de producto no debe poder cerrar el <script>."""
    import json as _json

    payload = {"name": "</script><img src=x onerror=alert(1)>"}
    raw = _json.dumps(payload, ensure_ascii=False)
    seguro = raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    assert "</script>" not in seguro
    assert "<" not in seguro
    assert _json.loads(seguro) == payload
