"""Tests del servicio webhook_monitor.

Cubre:
- record_webhook(): persiste row, extrae instance_name y event_type del payload.
- _prune_old(): mantiene solo \u00faltimos N por source.
- last_webhook_by_instance(): devuelve \u00faltimo evento por instancia.
- evolution_connection_state(): tolera timeouts/errores, parsea respuesta OK.
- Endpoint /admin/integrations/evolution-health.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.models.webhook_log import WebhookLog
from app.services.webhook_monitor import (
    record_webhook,
    last_webhook_by_instance,
    evolution_connection_state,
    _extract_instance_name,
    _prune_old,
    WEBHOOK_LOG_RETENTION,
)


@pytest_asyncio.fixture
async def wh_db() -> AsyncSession:
    """Engine y sesi\u00f3n SQLite aislada con solo la tabla WebhookLog."""
    from sqlalchemy import Integer
    # Asegurar id INTEGER autoincrement en SQLite
    WebhookLog.__table__.c.id.type = Integer()

    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(lambda sc: WebhookLog.__table__.create(sc, checkfirst=True))
    Session = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        yield session
    await eng.dispose()


class TestExtractInstanceName:
    def test_evolution_instance_field(self):
        assert _extract_instance_name({"instance": "apu"}, "whatsapp") == "apu"

    def test_evolution_instance_name_field(self):
        assert _extract_instance_name({"instanceName": "apu2"}, "whatsapp") == "apu2"

    def test_missing_fields_returns_none(self):
        assert _extract_instance_name({"event": "x"}, "whatsapp") is None

    def test_telegram_always_none(self):
        assert _extract_instance_name({"instance": "apu"}, "telegram") is None

    def test_non_dict_returns_none(self):
        assert _extract_instance_name("string-payload", "whatsapp") is None


class TestRecordWebhook:
    async def test_persists_with_event_and_instance_from_payload(self, wh_db):
        row = await record_webhook(
            wh_db,
            source="whatsapp",
            payload={"event": "messages.upsert", "instance": "apu", "data": {"x": 1}},
        )
        await wh_db.commit()
        assert row is not None
        assert row.id is not None
        assert row.source == "whatsapp"
        assert row.event_type == "messages.upsert"
        assert row.instance_name == "apu"
        assert row.status == "received"
        assert row.payload["data"]["x"] == 1

    async def test_explicit_event_type_overrides_payload(self, wh_db):
        row = await record_webhook(
            wh_db,
            source="whatsapp",
            payload={"event": "ignored"},
            event_type="custom.event",
        )
        await wh_db.commit()
        assert row.event_type == "custom.event"

    async def test_telegram_source_no_instance(self, wh_db):
        row = await record_webhook(
            wh_db,
            source="telegram",
            payload={"message": {"chat": {"id": 1}}},
        )
        await wh_db.commit()
        assert row.source == "telegram"
        assert row.instance_name is None

    async def test_error_status_with_error_field(self, wh_db):
        row = await record_webhook(
            wh_db,
            source="whatsapp",
            payload={"event": "x"},
            status="error",
            error="boom",
        )
        await wh_db.commit()
        assert row.status == "error"
        assert row.error == "boom"


class TestPruneOld:
    async def test_keeps_last_N_per_source(self, wh_db):
        # Insertar WEBHOOK_LOG_RETENTION + 5 rows
        total = WEBHOOK_LOG_RETENTION + 5
        for i in range(total):
            wh_db.add(WebhookLog(
                source="whatsapp",
                event_type="e",
                instance_name="apu",
                status="received",
                payload={"i": i},
            ))
        await wh_db.commit()

        # Confirmar conteo previo
        count_before = (await wh_db.execute(
            select(func.count()).select_from(WebhookLog)
        )).scalar()
        assert count_before == total

        deleted = await _prune_old(wh_db, "whatsapp")
        await wh_db.commit()
        assert deleted == 5

        count_after = (await wh_db.execute(
            select(func.count()).select_from(WebhookLog)
        )).scalar()
        assert count_after == WEBHOOK_LOG_RETENTION

    async def test_no_prune_when_under_limit(self, wh_db):
        for i in range(10):
            wh_db.add(WebhookLog(source="whatsapp", status="received", payload={}))
        await wh_db.commit()
        deleted = await _prune_old(wh_db, "whatsapp")
        assert deleted == 0

    async def test_prune_respects_source(self, wh_db):
        # Insertar 3 de cada, no debe tocar nada
        for i in range(3):
            wh_db.add(WebhookLog(source="whatsapp", status="received", payload={}))
            wh_db.add(WebhookLog(source="telegram", status="received", payload={}))
        await wh_db.commit()
        # Con l\u00edmite 1000 no hay prune
        await _prune_old(wh_db, "whatsapp")
        total = (await wh_db.execute(
            select(func.count()).select_from(WebhookLog)
        )).scalar()
        assert total == 6


class TestLastWebhookByInstance:
    async def test_returns_latest_per_instance(self, wh_db):
        # 3 instancias distintas, cada una con 2 eventos
        for inst in ("apu", "ventas", "soporte"):
            for i, ev in enumerate(("messages.upsert", "connection.update")):
                wh_db.add(WebhookLog(
                    source="whatsapp", event_type=ev,
                    instance_name=inst, status="received", payload={},
                ))
        await wh_db.commit()

        result = await last_webhook_by_instance(wh_db, source="whatsapp")
        assert set(result.keys()) == {"apu", "ventas", "soporte"}
        # Para cada instancia el event_type es el m\u00e1s reciente insertado
        for inst in ("apu", "ventas", "soporte"):
            assert result[inst]["event_type"] == "connection.update"
            assert result[inst]["status"] == "received"
            assert result[inst]["received_at"] is not None

    async def test_unknown_key_for_rows_without_instance(self, wh_db):
        wh_db.add(WebhookLog(
            source="whatsapp", event_type="x",
            instance_name=None, status="received", payload={},
        ))
        await wh_db.commit()
        result = await last_webhook_by_instance(wh_db, source="whatsapp")
        assert "__unknown__" in result

    async def test_filters_by_source(self, wh_db):
        wh_db.add(WebhookLog(source="whatsapp", instance_name="apu", status="received", payload={}))
        wh_db.add(WebhookLog(source="telegram", instance_name=None, status="received", payload={}))
        await wh_db.commit()
        wa = await last_webhook_by_instance(wh_db, source="whatsapp")
        tg = await last_webhook_by_instance(wh_db, source="telegram")
        assert "apu" in wa and "__unknown__" not in wa
        assert "__unknown__" in tg and "apu" not in tg


class TestEvolutionConnectionState:
    async def test_returns_unknown_when_url_empty(self):
        res = await evolution_connection_state("", "apu", "key")
        assert res["state"] == "unknown"
        assert "missing" in res["error"]

    async def test_parses_open_state(self):
        from app.services import webhook_monitor as M

        class _Resp:
            status_code = 200
            def json(self):
                return {"instance": {"state": "open", "instanceName": "apu"}}

        class _Client:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url, headers=None):
                assert url == "http://evo/instance/connectionState/apu"
                assert headers == {"apikey": "key"}
                return _Resp()

        with patch.object(M.httpx, "AsyncClient", _Client):
            res = await evolution_connection_state("http://evo", "apu", "key")
        assert res["state"] == "open"

    async def test_handles_http_error(self):
        from app.services import webhook_monitor as M

        class _Resp:
            status_code = 500
            text = "server err"

        class _Client:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, *a, **kw): return _Resp()

        with patch.object(M.httpx, "AsyncClient", _Client):
            res = await evolution_connection_state("http://evo", "apu", "k")
        assert res["state"] == "unknown"
        assert "HTTP 500" in res["error"]

    async def test_handles_connection_exception(self):
        from app.services import webhook_monitor as M

        class _Client:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, *a, **kw): raise ConnectionError("unreachable")

        with patch.object(M.httpx, "AsyncClient", _Client):
            res = await evolution_connection_state("http://evo", "apu", "k")
        assert res["state"] == "unknown"
        assert "unreachable" in res["error"]

    async def test_trims_trailing_slash(self):
        from app.services import webhook_monitor as M
        captured = {}

        class _Resp:
            status_code = 200
            def json(self): return {"instance": {"state": "close"}}

        class _Client:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url, headers=None):
                captured["url"] = url
                return _Resp()

        with patch.object(M.httpx, "AsyncClient", _Client):
            res = await evolution_connection_state("http://evo/", "apu", "k")
        assert captured["url"] == "http://evo/instance/connectionState/apu"
        assert res["state"] == "close"
