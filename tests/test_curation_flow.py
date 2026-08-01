"""Circuito completo de aporte curado, contra la API real.

Verifica la idea central del portal gratuito: alguien arma un presupuesto,
corrige un precio con una cotizacion real, y ese dato alimenta el catalogo
publico pasando por una compuerta que separa el aporte del error.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - shim de test
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_sqlite(type_, compiler, **kw):  # pragma: no cover - shim de test
    return "JSON"

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.apu import (
    ApuComputo, ApuItem, ApuItemSummary, ApuLine, ApuProject, ApuRubro,
    ApuTemplate, ApuTemplateLine,
)
from app.models.company import Company, Plan, Subscription
from app.models.company_insumo import CompanyInsumo, PriceSuggestion
from app.models.insumo import Insumo
from app.models.price_history import PriceHistory
from app.models.system_setting import SystemSetting
from app.models.user import User

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    tablas = [
        Company.__table__, Plan.__table__, Subscription.__table__,
        User.__table__, Insumo.__table__, PriceHistory.__table__,
        SystemSetting.__table__, CompanyInsumo.__table__, PriceSuggestion.__table__,
        ApuTemplate.__table__, ApuTemplateLine.__table__, ApuProject.__table__,
        ApuRubro.__table__, ApuItem.__table__, ApuLine.__table__,
        ApuComputo.__table__, ApuItemSummary.__table__,
    ]
    async with engine.begin() as conn:
        for t in tablas:
            await conn.run_sync(lambda c, tt=t: tt.create(c, checkfirst=True))

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        company = Company(name="Constructora A", country="BO", contributes_prices=True)
        db.add(company)
        await db.flush()
        db.add(Subscription(
            company_id=company.id, plan="professional", state="active",
            max_users=5, max_pedidos_month=50, max_projects=10,
            started_at=datetime.now(timezone.utc), grace_days=7,
        ))
        editor = User(
            email="a@test.bo", hashed_password="x", full_name="Editor",
            role="user", is_active=True, company_id=company.id,
            company_role="company_admin",
        )
        curador = User(
            email="staff@test.bo", hashed_password="x", full_name="Curador",
            role="admin", is_active=True,
        )
        db.add_all([editor, curador])

        cemento = Insumo(
            name="Cemento IP-30 50kg", name_normalized="cemento ip30 50kg",
            code="APUI-1", uom="bls", uom_normalized="bls", category="cemento",
            ref_price=57.60, ref_currency="BOB", is_active=True,
        )
        db.add(cemento)
        await db.flush()

        # Historico coherente: 5 observaciones alrededor de 57-59
        for i, precio in enumerate([57.0, 58.0, 57.5, 59.0, 58.5]):
            db.add(PriceHistory(
                insumo_id=cemento.id, unit_price=precio, currency="BOB",
                uom="bls", observed_date=date.today() - timedelta(days=30 * i),
                source="import",
            ))
        await db.commit()
        ids = {"company": company.id, "cemento": cemento.id}
        usuarios = {"editor": editor, "curador": curador}

    async def _get_db():
        async with Session() as s:
            yield s

    actual = {"user": usuarios["editor"]}
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: actual["user"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, ids, usuarios, actual, Session

    app.dependency_overrides.clear()
    await engine.dispose()


async def _armar_presupuesto(client, insumo_id, precio=None):
    r = await client.post("/api/v1/apu/projects", json={"name": "Obra", "region": "La Paz"})
    pid = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/apu/projects/{pid}/items", json={
        "name": "Partida", "uom": "m2",
    })
    iid = r.json()["data"]["id"]
    payload = {"type": "mat", "insumo_id": insumo_id, "quantity": 1.0}
    if precio is not None:
        payload["price_unit"] = precio
    r = await client.post(f"/api/v1/apu/items/{iid}/lines", json=payload)
    return pid, iid, r.json()["data"]["id"]


# ── Aporte coherente: entra solo ───────────────────────────────
async def test_precio_coherente_se_acepta_solo_y_alimenta_el_catalogo(env):
    client, ids, _, _, Session = env
    _, _, line_id = await _armar_presupuesto(client, ids["cemento"])

    # Cotizacion real: 58.20, coherente con el historico
    r = await client.put(f"/api/v1/apu/lines/{line_id}", json={"price_unit": 58.20})
    assert r.status_code == 200

    async with Session() as db:
        s = (await db.execute(select(PriceSuggestion))).scalars().all()
        assert len(s) == 1
        assert s[0].state == "auto_accepted"
        assert s[0].source == "budget"
        assert s[0].z_score is not None

        # Se materializo como observacion del historico
        obs = (await db.execute(
            select(PriceHistory).where(PriceHistory.source == "portal")
        )).scalars().all()
        assert len(obs) == 1
        assert obs[0].unit_price == 58.20


# ── Aporte sospechoso: revision humana ─────────────────────────
async def test_precio_muy_desviado_queda_pendiente_y_no_toca_el_catalogo(env):
    client, ids, _, _, Session = env
    _, _, line_id = await _armar_presupuesto(client, ids["cemento"])

    await client.put(f"/api/v1/apu/lines/{line_id}", json={"price_unit": 120.0})

    async with Session() as db:
        s = (await db.execute(select(PriceSuggestion))).scalars().one()
        assert s.state == "pending"
        assert s.z_score > 2.0

        # El catalogo NO se movio
        insumo = await db.get(Insumo, ids["cemento"])
        assert insumo.ref_price == 57.60
        obs = (await db.execute(
            select(PriceHistory).where(PriceHistory.source == "portal")
        )).scalars().all()
        assert obs == []


async def test_error_de_tipeo_no_entra_solo(env):
    client, ids, _, _, Session = env
    _, _, line_id = await _armar_presupuesto(client, ids["cemento"])

    await client.put(f"/api/v1/apu/lines/{line_id}", json={"price_unit": 5760.0})

    async with Session() as db:
        s = (await db.execute(select(PriceSuggestion))).scalars().one()
        assert s.state == "pending"
        assert "tipeo" in s.decision_reason


# ── Consentimiento ─────────────────────────────────────────────
async def test_empresa_que_no_aporta_no_genera_sugerencias(env):
    """El opt-in es real: sin consentimiento no sale ningun dato."""
    client, ids, _, _, Session = env
    async with Session() as db:
        company = await db.get(Company, ids["company"])
        company.contributes_prices = False
        await db.commit()

    _, _, line_id = await _armar_presupuesto(client, ids["cemento"])
    await client.put(f"/api/v1/apu/lines/{line_id}", json={"price_unit": 58.20})

    async with Session() as db:
        assert (await db.execute(select(PriceSuggestion))).scalars().all() == []


# ── Revision humana ────────────────────────────────────────────
async def test_el_curador_acepta_y_el_precio_se_publica_por_mediana(env):
    client, ids, usuarios, actual, Session = env
    _, _, line_id = await _armar_presupuesto(client, ids["cemento"])
    await client.put(f"/api/v1/apu/lines/{line_id}", json={"price_unit": 120.0})

    async with Session() as db:
        sid = (await db.execute(select(PriceSuggestion.id))).scalar_one()

    actual["user"] = usuarios["curador"]
    r = await client.post(f"/api/v1/company-insumos/suggestions/{sid}/accept",
                          json={"note": "Verificado con el proveedor"})
    assert r.status_code == 200
    assert r.json()["data"]["state"] == "accepted"

    async with Session() as db:
        insumo = await db.get(Insumo, ids["cemento"])
        # Publicado por MEDIANA, no por el ultimo dato. El historico era
        # [57.0, 57.5, 58.0, 58.5, 59.0] y entro 120.0: la mediana de las seis
        # observaciones es 58.25. Un outlier aceptado mueve el precio publico
        # unos centavos, no lo dispara.
        assert insumo.ref_price == 58.25
        assert insumo.ref_price < 60.0


async def test_el_curador_rechaza_y_no_pasa_nada(env):
    client, ids, usuarios, actual, Session = env
    _, _, line_id = await _armar_presupuesto(client, ids["cemento"])
    await client.put(f"/api/v1/apu/lines/{line_id}", json={"price_unit": 120.0})

    async with Session() as db:
        sid = (await db.execute(select(PriceSuggestion.id))).scalar_one()

    actual["user"] = usuarios["curador"]
    r = await client.post(f"/api/v1/company-insumos/suggestions/{sid}/reject",
                          json={"note": "Precio no verificable"})
    assert r.json()["data"]["state"] == "rejected"

    async with Session() as db:
        insumo = await db.get(Insumo, ids["cemento"])
        assert insumo.ref_price == 57.60


async def test_no_se_puede_resolver_dos_veces(env):
    client, ids, usuarios, actual, Session = env
    _, _, line_id = await _armar_presupuesto(client, ids["cemento"])
    await client.put(f"/api/v1/apu/lines/{line_id}", json={"price_unit": 120.0})
    async with Session() as db:
        sid = (await db.execute(select(PriceSuggestion.id))).scalar_one()

    actual["user"] = usuarios["curador"]
    await client.post(f"/api/v1/company-insumos/suggestions/{sid}/accept", json={})
    r = await client.post(f"/api/v1/company-insumos/suggestions/{sid}/reject", json={})
    assert r.status_code == 409


# ── Biblioteca de empresa ──────────────────────────────────────
async def test_biblioteca_propia_aislada_por_empresa(env):
    client, ids, _, _, Session = env
    r = await client.post("/api/v1/company-insumos", json={
        "name": "Ladrillo artesanal del valle", "type": "mat", "uom": "pza",
        "reference_price": 1.85,
    })
    assert r.status_code == 201
    assert r.json()["data"]["source_type"] == "manual"

    r = await client.get("/api/v1/company-insumos")
    assert r.json()["total"] == 1

    async with Session() as db:
        ci = (await db.execute(select(CompanyInsumo))).scalars().one()
        assert ci.company_id == ids["company"]


async def test_importar_del_catalogo_vincula_y_no_duplica(env):
    client, ids, _, _, Session = env
    r = await client.post(f"/api/v1/company-insumos/{ids['cemento']}/import-from-catalog")
    assert r.status_code == 201
    assert r.json()["already_existed"] is False
    assert r.json()["data"]["source_type"] == "catalog"
    assert r.json()["data"]["reference_price"] == 57.60

    r = await client.post(f"/api/v1/company-insumos/{ids['cemento']}/import-from-catalog")
    assert r.json()["already_existed"] is True


async def test_proponer_insumo_nuevo_al_catalogo(env):
    """El aporte por usar el portal gratis: compartir lo que falta."""
    client, ids, usuarios, actual, Session = env
    r = await client.post("/api/v1/company-insumos", json={
        "name": "Malla olimpica galvanizada 2m", "type": "mat", "uom": "ml",
        "reference_price": 42.0, "category": "ferreteria",
    })
    ci_id = r.json()["data"]["id"]

    r = await client.post(f"/api/v1/company-insumos/{ci_id}/propose-to-catalog")
    assert r.status_code == 200
    sid = r.json()["data"]["suggestion_id"]
    # Un alta SIEMPRE la mira un humano
    assert r.json()["data"]["state"] == "pending"

    actual["user"] = usuarios["curador"]
    r = await client.post(f"/api/v1/company-insumos/suggestions/{sid}/accept", json={})
    assert r.status_code == 200

    async with Session() as db:
        nuevo = (await db.execute(
            select(Insumo).where(Insumo.name == "Malla olimpica galvanizada 2m")
        )).scalar_one()
        # Se publica sin precio: hace falta mas de una observacion
        assert nuevo.ref_price is None
        ci = await db.get(CompanyInsumo, ci_id)
        assert ci.source_type == "catalog"
        assert ci.source_insumo_id == nuevo.id


async def test_no_se_propone_dos_veces(env):
    client, ids, _, _, _ = env
    r = await client.post("/api/v1/company-insumos", json={
        "name": "Item X", "type": "mat", "uom": "u", "reference_price": 10.0,
    })
    ci_id = r.json()["data"]["id"]
    await client.post(f"/api/v1/company-insumos/{ci_id}/propose-to-catalog")
    r = await client.post(f"/api/v1/company-insumos/{ci_id}/propose-to-catalog")
    assert r.status_code == 409


# ── Configuracion de la compuerta ──────────────────────────────
async def test_el_staff_ajusta_los_umbrales(env):
    client, ids, usuarios, actual, Session = env
    actual["user"] = usuarios["curador"]

    r = await client.put("/api/v1/company-insumos/suggestions/config", json={
        "z_auto": 0.5, "auto_accept_enabled": True,
    })
    assert r.status_code == 200
    assert r.json()["data"]["z_auto"] == 0.5

    # Con el umbral estricto, un precio antes aceptable ahora va a revision
    actual["user"] = usuarios["editor"]
    _, _, line_id = await _armar_presupuesto(client, ids["cemento"])
    await client.put(f"/api/v1/apu/lines/{line_id}", json={"price_unit": 60.0})

    async with Session() as db:
        s = (await db.execute(select(PriceSuggestion))).scalars().one()
        assert s.state == "pending"


async def test_la_cola_y_su_config_son_solo_para_staff(env):
    client, ids, usuarios, actual, _ = env
    actual["user"] = usuarios["editor"]  # no es staff

    for method, path in [
        ("get", "/api/v1/company-insumos/suggestions/queue"),
        ("get", "/api/v1/company-insumos/suggestions/config"),
        ("put", "/api/v1/company-insumos/suggestions/config"),
        ("post", "/api/v1/company-insumos/suggestions/1/accept"),
        ("post", "/api/v1/company-insumos/suggestions/1/reject"),
    ]:
        r = await client.request(method.upper(), path, json={})
        assert r.status_code == 403, f"{path} -> {r.status_code}"
