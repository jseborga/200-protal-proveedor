"""Tests del endpoint /api/v1/inbox/metrics (5.2 dashboard SLA).

Cubre:
- Contadores de abiertas / asignadas / sin asignar / pendientes.
- sla_breach calculado contra last_client_msg_at.
- first_response_avg_seconds entre primer inbound y primer outbound operator.
- resolution_avg_hours sobre sesiones cerradas en la ventana.
- volume_by_day agrupado por dia.
- by_operator con deltas por operador.
- Auth: require_staff.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import require_staff
from app.core.database import get_db
from app.api.routes.inbox import router as inbox_router
from app.models.conversation import ConversationSession, Message
from app.models.user import User
from app.models.pedido import Pedido


@pytest_asyncio.fixture
async def staff_user(db) -> User:
    u = User(
        email="staff@test.com",
        hashed_password="x",
        full_name="Staff Tester",
        role="manager",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def operator_a(db) -> User:
    u = User(
        email="opa@test.com", hashed_password="x",
        full_name="Op A", role="agent", is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def operator_b(db) -> User:
    u = User(
        email="opb@test.com", hashed_password="x",
        full_name="Op B", role="agent", is_active=True,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def app(db, staff_user):
    app = FastAPI()
    app.include_router(inbox_router, prefix="/api/v1/inbox")

    async def _get_db_override():
        yield db

    async def _require_staff_override():
        return staff_user

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[require_staff] = _require_staff_override
    yield app
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _make_pedido(db, creator: User, ref: str) -> Pedido:
    p = Pedido(
        reference=ref, title="T",
        description="", state="active",
        created_by=creator.id, currency="BOB",
        client_whatsapp="+591 71234567",
        item_count=0, quotes_received=0,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


class TestMetricsCounters:
    async def test_empty_db_returns_zeros(self, client):
        resp = await client.get("/api/v1/inbox/metrics")
        assert resp.status_code == 200
        d = resp.json()["data"]
        assert d["open_sessions"] == 0
        assert d["open_unassigned"] == 0
        assert d["open_assigned"] == 0
        assert d["pending_response"] == 0
        assert d["sla_breach"] == 0
        assert d["first_response_avg_seconds"] is None
        assert d["resolution_avg_hours"] is None
        assert d["volume_by_day"] == []
        assert d["by_operator"] == []

    async def test_open_and_assignment_counts(self, client, db, staff_user, operator_a):
        p1 = await _make_pedido(db, staff_user, "P-1")
        p2 = await _make_pedido(db, staff_user, "P-2")
        p3 = await _make_pedido(db, staff_user, "P-3")
        # 1 abierta sin asignar, 1 asignada, 1 cerrada
        db.add(ConversationSession(pedido_id=p1.id, state="active", operator_id=None))
        db.add(ConversationSession(pedido_id=p2.id, state="active", operator_id=operator_a.id))
        db.add(ConversationSession(pedido_id=p3.id, state="closed", operator_id=operator_a.id))
        await db.commit()

        resp = await client.get("/api/v1/inbox/metrics")
        d = resp.json()["data"]
        assert d["open_sessions"] == 2
        assert d["open_unassigned"] == 1
        assert d["open_assigned"] == 1

    async def test_pending_and_sla_breach(self, client, db, staff_user, operator_a):
        p1 = await _make_pedido(db, staff_user, "P-1")
        p2 = await _make_pedido(db, staff_user, "P-2")
        now = datetime.now(timezone.utc)

        # Pendiente reciente (<1h): no sla_breach
        s1 = ConversationSession(
            pedido_id=p1.id, state="active", operator_id=operator_a.id,
            last_client_msg_at=now - timedelta(minutes=10),
            last_operator_msg_at=None,
        )
        # Pendiente viejo (3h): sla_breach con threshold 1h
        s2 = ConversationSession(
            pedido_id=p2.id, state="active", operator_id=operator_a.id,
            last_client_msg_at=now - timedelta(hours=3),
            last_operator_msg_at=now - timedelta(hours=4),  # op respondio antes del ultimo cliente
        )
        db.add_all([s1, s2])
        await db.commit()

        resp = await client.get("/api/v1/inbox/metrics?sla_hours=1")
        d = resp.json()["data"]
        assert d["pending_response"] == 2
        assert d["sla_breach"] == 1


class TestFirstResponseAvg:
    async def test_avg_between_inbound_and_operator_outbound(
        self, client, db, staff_user, operator_a
    ):
        now = datetime.now(timezone.utc)
        p = await _make_pedido(db, staff_user, "P-1")
        s = ConversationSession(
            pedido_id=p.id, state="active", operator_id=operator_a.id,
            last_client_msg_at=now,
        )
        db.add(s)
        await db.commit()
        await db.refresh(s)

        # Primer inbound en t0, primer outbound-operator 60s despues
        m1 = Message(
            session_id=s.id, direction="inbound", channel="whatsapp",
            sender_type="client", body="hola",
            created_at=now - timedelta(seconds=120),
        )
        m2 = Message(
            session_id=s.id, direction="outbound", channel="whatsapp",
            sender_type="operator", body="hola!",
            created_at=now - timedelta(seconds=60),
        )
        db.add_all([m1, m2])
        await db.commit()

        resp = await client.get("/api/v1/inbox/metrics?days=7")
        d = resp.json()["data"]
        assert d["first_response_samples"] == 1
        assert d["first_response_avg_seconds"] is not None
        # Aproximadamente 60s
        assert abs(d["first_response_avg_seconds"] - 60) < 5

    async def test_ignores_bot_outbound(self, client, db, staff_user):
        """Si solo hay outbound bot (no operator), no cuenta."""
        now = datetime.now(timezone.utc)
        p = await _make_pedido(db, staff_user, "P-1")
        s = ConversationSession(pedido_id=p.id, state="active")
        db.add(s)
        await db.commit()
        await db.refresh(s)

        db.add(Message(
            session_id=s.id, direction="inbound", channel="whatsapp",
            sender_type="client", body="hola",
            created_at=now - timedelta(seconds=120),
        ))
        db.add(Message(
            session_id=s.id, direction="outbound", channel="whatsapp",
            sender_type="bot", body="auto",
            created_at=now - timedelta(seconds=60),
        ))
        await db.commit()

        resp = await client.get("/api/v1/inbox/metrics")
        d = resp.json()["data"]
        assert d["first_response_samples"] == 0
        assert d["first_response_avg_seconds"] is None


class TestResolutionAvg:
    async def test_avg_hours_over_closed_sessions(
        self, client, db, staff_user, operator_a
    ):
        p = await _make_pedido(db, staff_user, "P-1")
        now = datetime.now(timezone.utc)
        # Sesion creada hace 2h y cerrada ahora -> 2h de resolucion
        s = ConversationSession(
            pedido_id=p.id, state="closed", operator_id=operator_a.id,
        )
        db.add(s)
        await db.commit()
        await db.refresh(s)
        # Forzar timestamps (SQLAlchemy puede no respetar si los seteamos antes)
        s.created_at = now - timedelta(hours=2)
        s.updated_at = now
        await db.commit()

        resp = await client.get("/api/v1/inbox/metrics")
        d = resp.json()["data"]
        assert d["resolution_samples"] == 1
        assert d["resolution_avg_hours"] is not None
        assert abs(d["resolution_avg_hours"] - 2.0) < 0.1


class TestVolumeByDay:
    async def test_groups_inbound_per_day(self, client, db, staff_user):
        p = await _make_pedido(db, staff_user, "P-1")
        s = ConversationSession(pedido_id=p.id, state="active")
        db.add(s)
        await db.commit()
        await db.refresh(s)
        now = datetime.now(timezone.utc)
        # 2 inbound hoy, 1 ayer
        db.add(Message(
            session_id=s.id, direction="inbound", channel="whatsapp",
            sender_type="client", body="a", created_at=now,
        ))
        db.add(Message(
            session_id=s.id, direction="inbound", channel="whatsapp",
            sender_type="client", body="b", created_at=now - timedelta(minutes=30),
        ))
        db.add(Message(
            session_id=s.id, direction="inbound", channel="whatsapp",
            sender_type="client", body="c", created_at=now - timedelta(days=1),
        ))
        # outbound no cuenta
        db.add(Message(
            session_id=s.id, direction="outbound", channel="whatsapp",
            sender_type="operator", body="x", created_at=now,
        ))
        await db.commit()

        resp = await client.get("/api/v1/inbox/metrics?days=7")
        d = resp.json()["data"]
        total = sum(x["count"] for x in d["volume_by_day"])
        assert total == 3


class TestByOperator:
    async def test_breakdown_per_operator(
        self, client, db, staff_user, operator_a, operator_b
    ):
        now = datetime.now(timezone.utc)
        pA = await _make_pedido(db, staff_user, "P-A")
        pB = await _make_pedido(db, staff_user, "P-B")
        sA = ConversationSession(pedido_id=pA.id, state="active", operator_id=operator_a.id)
        sB = ConversationSession(pedido_id=pB.id, state="closed", operator_id=operator_b.id)
        db.add_all([sA, sB])
        await db.commit()
        sB.updated_at = now  # forzar dentro de ventana

        db.add(Message(
            session_id=sA.id, direction="inbound", channel="whatsapp",
            sender_type="client", created_at=now - timedelta(seconds=200),
        ))
        db.add(Message(
            session_id=sA.id, direction="outbound", channel="whatsapp",
            sender_type="operator", created_at=now - timedelta(seconds=100),
        ))
        await db.commit()

        resp = await client.get("/api/v1/inbox/metrics")
        d = resp.json()["data"]
        by_op = {r["operator_id"]: r for r in d["by_operator"]}
        assert operator_a.id in by_op
        assert by_op[operator_a.id]["open"] == 1
        assert by_op[operator_a.id]["responses_counted"] == 1
        assert operator_b.id in by_op
        assert by_op[operator_b.id]["closed_in_window"] == 1


class TestAuthRequired:
    async def test_requires_staff(self, db):
        """Sin override de require_staff, endpoint rechaza."""
        app = FastAPI()
        app.include_router(inbox_router, prefix="/api/v1/inbox")

        async def _get_db_override():
            yield db

        app.dependency_overrides[get_db] = _get_db_override
        # NO overridear require_staff

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/inbox/metrics")
        assert resp.status_code in (401, 403)
