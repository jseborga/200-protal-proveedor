"""Prueba de extremo a extremo del modulo APU contra la API real.

Levanta un SQLite propio con las tablas del modulo, un usuario con empresa y
una suscripcion, y recorre el flujo completo que hace la interfaz: crear
proyecto, rubro, partida, agregar recursos, computos metricos, recalcular y
consultar el resumen de recursos.

Sirve para dos cosas: verificar que los numeros salen bien de punta a punta y
fijar el contrato que consume el frontend (mat/mo/eq, formas de respuesta).
"""
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles


# Los modelos usan tipos de Postgres que SQLite no sabe compilar. Se les da un
# equivalente SOLO para los tests; los modelos de produccion no se tocan.
@compiles(JSONB, "sqlite")
def _jsonb_en_sqlite(type_, compiler, **kw):  # pragma: no cover - shim de test
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_en_sqlite(type_, compiler, **kw):  # pragma: no cover - shim de test
    return "JSON"

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.apu import (
    ApuComputo, ApuItem, ApuItemSummary, ApuLine, ApuProject, ApuRubro,
    ApuTemplate, ApuTemplateLine,
)
from app.models.company import Company, Plan, Subscription
from app.models.insumo import Insumo
from app.models.user import User

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def apu_env():
    """Base con el esquema del modulo + empresa, usuario, plantilla e insumos."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    tablas = [
        Company.__table__, Plan.__table__, Subscription.__table__,
        User.__table__, Insumo.__table__,
        ApuTemplate.__table__, ApuTemplateLine.__table__, ApuProject.__table__,
        ApuRubro.__table__, ApuItem.__table__, ApuLine.__table__,
        ApuComputo.__table__, ApuItemSummary.__table__,
    ]
    async with engine.begin() as conn:
        for t in tablas:
            await conn.run_sync(lambda c, tt=t: tt.create(c, checkfirst=True))

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        company = Company(name="Constructora Test", country="BO")
        db.add(company)
        await db.flush()

        db.add(Subscription(
            company_id=company.id, plan="professional", state="active",
            max_users=5, max_pedidos_month=50, max_projects=10,
            started_at=datetime.now(timezone.utc), grace_days=7,
        ))

        user = User(
            email="jefe@test.bo", hashed_password="x", full_name="Jefe de obra",
            role="user", is_active=True, company_id=company.id,
            company_role="company_admin",
        )
        db.add(user)

        # Plantilla: cargas sociales sobre mano de obra + utilidad.
        template = ApuTemplate(company_id=None, name="Test GAMLP")
        db.add(template)
        await db.flush()
        for seq, (code, name, ltype, value, formula, total) in enumerate([
            ("MAT", "Materiales", "sum_mat", 0.0, None, False),
            ("MO", "Mano de obra", "sum_mo", 0.0, None, False),
            ("EQ", "Equipo", "sum_eq", 0.0, None, False),
            ("B1", "Cargas sociales", "percent", 71.18, "MO", False),
            ("C", "Costo directo", "formula", 0.0, "MAT + MO + EQ + B1", False),
            ("U", "Utilidad", "percent", 10.0, "C", False),
            ("T", "Precio unitario", "formula", 0.0, "C + U", True),
        ], 1):
            db.add(ApuTemplateLine(
                template_id=template.id, sequence=seq * 10, code=code, name=name,
                type=ltype, value=value, formula=formula, is_total=total,
            ))

        cemento = Insumo(
            name="Cemento IP-30 50kg", name_normalized="cemento ip30 50kg",
            code="APUI-1", uom="bls", uom_normalized="bls", category="cemento",
            ref_price=57.60, ref_currency="BOB", is_active=True,
        )
        albanil = Insumo(
            name="Albanil", name_normalized="albanil", code="APUI-MO-1",
            uom="hr", uom_normalized="hr", category="mano_obra",
            ref_price=18.75, ref_currency="BOB", is_active=True,
        )
        db.add_all([cemento, albanil])
        await db.commit()

        ids = {
            "company": company.id, "user": user.id, "template": template.id,
            "cemento": cemento.id, "albanil": albanil.id,
        }
        usuario = user

    async def _get_db():
        async with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: usuario

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, ids

    app.dependency_overrides.clear()
    await engine.dispose()


async def test_flujo_completo_de_presupuesto(apu_env):
    """Crea una obra, la compone y verifica el precio unitario resultante."""
    client, ids = apu_env

    # 1. Proyecto
    r = await client.post("/api/v1/apu/projects", json={
        "name": "Vivienda unifamiliar", "code": "OBRA-01",
        "client_name": "Cliente Test", "region": "La Paz",
        "template_id": ids["template"],
    })
    assert r.status_code == 201, r.text
    project_id = r.json()["data"]["id"]

    # 2. Rubro
    r = await client.post(f"/api/v1/apu/projects/{project_id}/rubros", json={
        "name": "Obra gruesa", "code": "2", "sequence": 10,
    })
    assert r.status_code == 201
    rubro_id = r.json()["data"]["id"]

    # 3. Partida
    r = await client.post(f"/api/v1/apu/projects/{project_id}/items", json={
        "name": "Muro de ladrillo visto", "uom": "m2", "code": "2.1",
        "rubro_id": rubro_id,
    })
    assert r.status_code == 201
    item_id = r.json()["data"]["id"]

    # 4. Recursos: material del catalogo (toma el precio de mercado)
    r = await client.post(f"/api/v1/apu/items/{item_id}/lines", json={
        "type": "mat", "insumo_id": ids["cemento"], "quantity": 0.25,
    })
    assert r.status_code == 201, r.text
    linea_mat = r.json()["data"]
    assert linea_mat["price_unit"] == 57.60      # copiado del catalogo
    assert linea_mat["price_source"] == "market"
    assert linea_mat["name"] == "Cemento IP-30 50kg"
    assert linea_mat["price_subtotal"] == 14.40  # 0.25 * 57.60

    # 5. Mano de obra
    r = await client.post(f"/api/v1/apu/items/{item_id}/lines", json={
        "type": "mo", "insumo_id": ids["albanil"], "quantity": 2.0,
    })
    assert r.status_code == 201
    assert r.json()["data"]["price_subtotal"] == 37.50  # 2 * 18.75

    # 6. Computos metricos: 2 muros de 5 x 2.5 m
    r = await client.post(f"/api/v1/apu/items/{item_id}/computos", json={
        "name": "Muros eje A", "pieces": 2, "length": 5.0, "width": 2.5, "height": 1.0,
    })
    assert r.status_code == 201
    assert r.json()["data"]["subtotal"] == 25.0

    # 7. Recalcular
    r = await client.post(f"/api/v1/apu/projects/{project_id}/recompute")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["cycles"] == []

    # 8. Verificar el APU resultante
    r = await client.get(f"/api/v1/apu/items/{item_id}")
    data = r.json()["data"]

    assert data["mat_cost"] == 14.40
    assert data["mo_cost"] == 37.50
    assert data["direct_cost"] == 51.90
    # La cantidad la fijan los computos metricos
    assert data["quantity"] == 25.0

    # Precio unitario segun la plantilla:
    #   B1 = 37.50 * 71.18% = 26.69
    #   C  = 14.40 + 37.50 + 0 + 26.69 = 78.59
    #   U  = 7.86 ; T = 86.45
    assert data["unit_price"] == 86.45
    assert data["total_price"] == 86.45 * 25.0

    # La planilla se materializa fila por fila
    codigos = [s["code"] for s in data["summary"]]
    assert codigos == ["MAT", "MO", "EQ", "B1", "C", "U", "T"]
    assert [s for s in data["summary"] if s["is_total"]][0]["code"] == "T"

    # 9. El total del proyecto refleja la partida
    r = await client.get(f"/api/v1/apu/projects/{project_id}")
    assert r.json()["data"]["total_budget"] == 2161.25
    assert r.json()["data"]["rubros"][0]["total"] == 2161.25


async def test_resumen_de_recursos_multiplica_por_la_cantidad(apu_env):
    """El requerimiento es rendimiento x cantidad de la partida."""
    client, ids = apu_env

    r = await client.post("/api/v1/apu/projects", json={
        "name": "Obra", "template_id": ids["template"],
    })
    project_id = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/apu/projects/{project_id}/items", json={
        "name": "Partida", "uom": "m2", "quantity": 10.0,
    })
    item_id = r.json()["data"]["id"]
    await client.post(f"/api/v1/apu/items/{item_id}/lines", json={
        "type": "mat", "insumo_id": ids["cemento"], "quantity": 0.5,
    })
    await client.post(f"/api/v1/apu/projects/{project_id}/recompute")

    r = await client.get(f"/api/v1/apu/projects/{project_id}/resources")
    assert r.status_code == 200
    recursos = r.json()["data"]
    assert len(recursos) == 1
    # 0.5 bolsas por m2 x 10 m2 = 5 bolsas
    assert recursos[0]["quantity"] == 5.0
    assert recursos[0]["amount"] == 288.0  # 5 * 57.60
    assert r.json()["totals"]["mat"] == 288.0


async def test_refrescar_precios_respeta_los_negociados_a_mano(apu_env):
    """Un precio negociado con un proveedor no se pisa en silencio."""
    client, ids = apu_env

    r = await client.post("/api/v1/apu/projects", json={"name": "Obra"})
    project_id = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/apu/projects/{project_id}/items", json={
        "name": "Partida", "uom": "m2",
    })
    item_id = r.json()["data"]["id"]

    # Recurso con precio negociado a mano, distinto del de mercado
    r = await client.post(f"/api/v1/apu/items/{item_id}/lines", json={
        "type": "mat", "insumo_id": ids["cemento"], "quantity": 1.0,
        "price_unit": 50.0,
    })
    assert r.json()["data"]["price_source"] == "manual"

    # Por defecto el precio manual se conserva
    r = await client.post(f"/api/v1/apu/projects/{project_id}/refresh-prices")
    assert r.status_code == 200
    assert r.json()["data"]["updated"] == 0
    assert r.json()["data"]["kept_manual"] == 1

    r = await client.get(f"/api/v1/apu/items/{item_id}")
    assert r.json()["data"]["lines"][0]["price_unit"] == 50.0

    # Con include_manual=true el usuario fuerza el alineado al mercado
    r = await client.post(
        f"/api/v1/apu/projects/{project_id}/refresh-prices?include_manual=true"
    )
    assert r.json()["data"]["updated"] == 1

    r = await client.get(f"/api/v1/apu/items/{item_id}")
    assert r.json()["data"]["lines"][0]["price_unit"] == 57.60


async def test_no_se_puede_agregar_recurso_de_tipo_invalido(apu_env):
    client, ids = apu_env
    r = await client.post("/api/v1/apu/projects", json={"name": "Obra"})
    project_id = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/apu/projects/{project_id}/items", json={
        "name": "Partida", "uom": "m2",
    })
    item_id = r.json()["data"]["id"]

    # 'material' es el nombre que usa la UI internamente; la API espera 'mat'
    r = await client.post(f"/api/v1/apu/items/{item_id}/lines", json={
        "type": "material", "name": "X", "quantity": 1, "price_unit": 1,
    })
    assert r.status_code == 400


async def test_una_partida_no_puede_consumirse_a_si_misma(apu_env):
    client, ids = apu_env
    r = await client.post("/api/v1/apu/projects", json={"name": "Obra"})
    project_id = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/apu/projects/{project_id}/items", json={
        "name": "Partida", "uom": "m2",
    })
    item_id = r.json()["data"]["id"]

    r = await client.post(f"/api/v1/apu/items/{item_id}/lines", json={
        "type": "sub", "linked_item_id": item_id, "quantity": 1,
    })
    assert r.status_code == 400


async def test_el_limite_de_proyectos_del_plan_se_aplica(apu_env):
    """Con max_projects=10, el proyecto 11 debe dar 402."""
    client, ids = apu_env

    for i in range(10):
        r = await client.post("/api/v1/apu/projects", json={"name": f"Obra {i}"})
        assert r.status_code == 201

    r = await client.post("/api/v1/apu/projects", json={"name": "Obra de mas"})
    assert r.status_code == 402
    assert "limite" in r.json()["detail"].lower()


# ══════════════════════════════════════════════════════════════
# Alcance de plantillas: global -> empresa -> proyecto
# ══════════════════════════════════════════════════════════════
async def test_las_globales_se_ven_pero_no_se_editan(apu_env):
    """Editar una global cambiaria el calculo de todas las empresas."""
    client, ids = apu_env

    r = await client.get("/api/v1/apu/templates")
    assert r.status_code == 200
    globales = [t for t in r.json()["data"] if t["scope"] == "global"]
    assert globales, "la plantilla de prueba es global"
    assert globales[0]["editable"] is False

    r = await client.put(f"/api/v1/apu/templates/{ids['template']}", json={
        "name": "Intento de cambio",
    })
    assert r.status_code == 403
    assert "clon" in r.json()["detail"].lower()

    r = await client.delete(f"/api/v1/apu/templates/{ids['template']}")
    assert r.status_code == 403


async def test_clonar_una_global_la_vuelve_privada_y_editable(apu_env):
    """Es el camino previsto: partir de una estructura conocida y ajustarla."""
    client, ids = apu_env

    r = await client.post(f"/api/v1/apu/templates/{ids['template']}/clone", json={
        "name": "GAMLP ajustada",
    })
    assert r.status_code == 201
    copia = r.json()["data"]
    assert copia["scope"] == "company"
    assert copia["editable"] is True
    assert copia["source_template_id"] == ids["template"]
    # Se copiaron todas las filas
    assert len(copia["lines"]) == 7

    # Y ahora si se puede ajustar el porcentaje de utilidad
    lineas = copia["lines"]
    for l in lineas:
        if l["code"] == "U":
            l["value"] = 15.0
    r = await client.put(f"/api/v1/apu/templates/{copia['id']}", json={"lines": lineas})
    assert r.status_code == 200
    assert [l for l in r.json()["data"]["lines"] if l["code"] == "U"][0]["value"] == 15.0


async def test_plantilla_privada_de_una_obra(apu_env):
    """Un contrato puede exigir porcentajes distintos solo para esa obra."""
    client, ids = apu_env

    r = await client.post("/api/v1/apu/projects", json={"name": "Obra especial"})
    project_id = r.json()["data"]["id"]

    r = await client.post(f"/api/v1/apu/templates/{ids['template']}/clone", json={
        "name": "Solo para esta obra", "project_id": project_id,
    })
    assert r.status_code == 201
    assert r.json()["data"]["scope"] == "project"
    assert r.json()["data"]["project_id"] == project_id

    # No aparece en el listado general...
    nombres = [t["name"] for t in (await client.get("/api/v1/apu/templates")).json()["data"]]
    assert "Solo para esta obra" not in nombres

    # ...pero si al pedir el contexto de esa obra
    r = await client.get(f"/api/v1/apu/templates?project_id={project_id}")
    assert "Solo para esta obra" in [t["name"] for t in r.json()["data"]]


async def test_no_se_guarda_una_plantilla_invalida(apu_env):
    """Se valida al guardar, no al recalcular: si no, rompe el presupuesto."""
    client, ids = apu_env

    r = await client.post("/api/v1/apu/templates", json={
        "name": "Rota",
        "lines": [
            {"code": "A", "name": "A", "type": "formula",
             "formula": "NO_EXISTE + 1", "sequence": 10},
        ],
    })
    assert r.status_code == 422
    assert "NO_EXISTE" in r.json()["detail"]


async def test_no_se_borra_una_plantilla_en_uso(apu_env):
    client, ids = apu_env

    r = await client.post(f"/api/v1/apu/templates/{ids['template']}/clone", json={})
    tid = r.json()["data"]["id"]
    await client.post("/api/v1/apu/projects", json={"name": "Usa la copia", "template_id": tid})

    r = await client.delete(f"/api/v1/apu/templates/{tid}")
    assert r.status_code == 409
    assert "usando" in r.json()["detail"]
