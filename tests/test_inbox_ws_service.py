"""Tests unit Fase 5.11: broadcaster in-memory del inbox WS."""
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import asyncio
from typing import Any

import pytest
import pytest_asyncio
from starlette.websockets import WebSocketState

from app.services import inbox_ws


class FakeWebSocket:
    """Minimal stub de WebSocket para tests."""

    def __init__(self, fail_on_send: bool = False):
        self.sent: list[dict] = []
        self.fail_on_send = fail_on_send
        self.client_state = WebSocketState.CONNECTED
        self.application_state = WebSocketState.CONNECTED

    async def send_json(self, payload: dict) -> None:
        if self.fail_on_send:
            raise RuntimeError("socket muerto")
        self.sent.append(payload)


@pytest_asyncio.fixture(autouse=True)
async def _reset_inbox_ws_state():
    await inbox_ws._reset_state()
    yield
    await inbox_ws._reset_state()


class TestRegisterUnregister:
    async def test_register_creates_entry(self):
        ws = FakeWebSocket()
        await inbox_ws.register_subscriber(7, ws, role="field_agent")
        assert inbox_ws.connected_users_count() == 1
        assert inbox_ws.total_sockets_count() == 1

    async def test_register_multiple_sockets_same_user(self):
        a, b = FakeWebSocket(), FakeWebSocket()
        await inbox_ws.register_subscriber(7, a, role="field_agent")
        await inbox_ws.register_subscriber(7, b, role="field_agent")
        assert inbox_ws.connected_users_count() == 1
        assert inbox_ws.total_sockets_count() == 2

    async def test_unregister_removes_socket(self):
        ws = FakeWebSocket()
        await inbox_ws.register_subscriber(7, ws, role="manager")
        await inbox_ws.unregister_subscriber(7, ws)
        assert inbox_ws.connected_users_count() == 0
        assert inbox_ws.total_sockets_count() == 0

    async def test_unregister_with_multiple_keeps_others(self):
        a, b = FakeWebSocket(), FakeWebSocket()
        await inbox_ws.register_subscriber(7, a, role="admin")
        await inbox_ws.register_subscriber(7, b, role="admin")
        await inbox_ws.unregister_subscriber(7, a)
        assert inbox_ws.connected_users_count() == 1
        assert inbox_ws.total_sockets_count() == 1


class TestBroadcast:
    async def test_broadcast_sends_to_all_sockets_of_user(self):
        a, b = FakeWebSocket(), FakeWebSocket()
        await inbox_ws.register_subscriber(7, a, role="field_agent")
        await inbox_ws.register_subscriber(7, b, role="field_agent")
        n = await inbox_ws.broadcast_to_user(7, {"x": 1})
        assert n == 2
        assert a.sent == [{"x": 1}]
        assert b.sent == [{"x": 1}]

    async def test_broadcast_to_unknown_user_returns_zero(self):
        n = await inbox_ws.broadcast_to_user(9999, {"x": 1})
        assert n == 0

    async def test_broadcast_removes_dead_sockets(self):
        alive = FakeWebSocket()
        dead = FakeWebSocket(fail_on_send=True)
        await inbox_ws.register_subscriber(7, alive, role="manager")
        await inbox_ws.register_subscriber(7, dead, role="manager")
        n = await inbox_ws.broadcast_to_user(7, {"x": 1})
        assert n == 1
        assert alive.sent == [{"x": 1}]
        # dead socket fue removido
        assert inbox_ws.total_sockets_count() == 1


class TestPublishEvent:
    async def test_payload_has_standard_envelope(self):
        ws = FakeWebSocket()
        await inbox_ws.register_subscriber(7, ws, role="field_agent")
        await inbox_ws.publish_event("session.claimed", {"session_id": 42})
        assert len(ws.sent) == 1
        payload = ws.sent[0]
        assert payload["type"] == "inbox_event"
        assert payload["event"] == "session.claimed"
        assert payload["data"] == {"session_id": 42}
        assert "ts" in payload and "T" in payload["ts"]  # ISO8601

    async def test_excludes_emitter_user(self):
        a = FakeWebSocket()
        b = FakeWebSocket()
        await inbox_ws.register_subscriber(1, a, role="manager")
        await inbox_ws.register_subscriber(2, b, role="manager")
        n = await inbox_ws.publish_event(
            "session.claimed", {"session_id": 42}, exclude_user_id=1
        )
        assert n == 1
        assert a.sent == []
        assert len(b.sent) == 1

    async def test_filters_by_target_roles(self):
        a = FakeWebSocket()
        b = FakeWebSocket()
        await inbox_ws.register_subscriber(1, a, role="field_agent")
        await inbox_ws.register_subscriber(2, b, role="manager")
        n = await inbox_ws.publish_event(
            "session.claimed", {"session_id": 42}, target_roles={"manager"}
        )
        assert n == 1
        assert a.sent == []
        assert len(b.sent) == 1

    async def test_default_target_roles_is_staff(self):
        a = FakeWebSocket()
        b = FakeWebSocket()
        # buyer NO es staff -> no recibe aunque este suscrito
        await inbox_ws.register_subscriber(1, a, role="buyer")
        await inbox_ws.register_subscriber(2, b, role="field_agent")
        n = await inbox_ws.publish_event("session.claimed", {"session_id": 42})
        assert n == 1
        assert a.sent == []
        assert len(b.sent) == 1

    async def test_swallows_internal_errors(self, monkeypatch):
        """publish_event NUNCA debe propagar excepciones."""

        async def explode(*a, **kw):
            raise RuntimeError("boom")

        monkeypatch.setattr(inbox_ws, "broadcast_to_user", explode)
        ws = FakeWebSocket()
        await inbox_ws.register_subscriber(1, ws, role="admin")
        # No debe lanzar
        n = await inbox_ws.publish_event("session.claimed", {"session_id": 42})
        assert n == 0


class TestSemanticHelpers:
    """Fase 5.11: wrappers semanticos consolidados (4 familias)."""

    async def test_publish_message_created_envelope(self):
        ws = FakeWebSocket()
        await inbox_ws.register_subscriber(7, ws, role="field_agent")
        n = await inbox_ws.publish_message_created(
            session_id=42, message_id=99, kind="inbound", preview="hola mundo"
        )
        assert n == 1
        p = ws.sent[0]
        assert p["event"] == "message.created"
        assert p["data"] == {
            "session_id": 42,
            "kind": "inbound",
            "message_id": 99,
            "preview": "hola mundo",
        }

    async def test_publish_message_created_rejects_invalid_kind(self):
        ws = FakeWebSocket()
        await inbox_ws.register_subscriber(7, ws, role="field_agent")
        n = await inbox_ws.publish_message_created(
            session_id=42, message_id=None, kind="bogus"
        )
        assert n == 0
        assert ws.sent == []

    async def test_publish_message_created_truncates_preview(self):
        ws = FakeWebSocket()
        await inbox_ws.register_subscriber(7, ws, role="field_agent")
        long = "x" * 300
        await inbox_ws.publish_message_created(
            session_id=1, message_id=1, kind="note", preview=long
        )
        assert len(ws.sent[0]["data"]["preview"]) == 140

    async def test_publish_operator_changed_envelope(self):
        ws = FakeWebSocket()
        await inbox_ws.register_subscriber(7, ws, role="manager")
        n = await inbox_ws.publish_session_operator_changed(
            session_id=42,
            prev_operator_id=None,
            operator_id=3,
            reason="claim",
            by_user_id=3,
        )
        assert n == 1
        p = ws.sent[0]
        assert p["event"] == "session.operator_changed"
        assert p["data"] == {
            "session_id": 42,
            "prev_operator_id": None,
            "operator_id": 3,
            "reason": "claim",
            "by_user_id": 3,
        }

    async def test_publish_operator_changed_with_strategy(self):
        ws = FakeWebSocket()
        await inbox_ws.register_subscriber(7, ws, role="admin")
        await inbox_ws.publish_session_operator_changed(
            session_id=1,
            prev_operator_id=2,
            operator_id=4,
            reason="auto_handoff",
            strategy="least_loaded",
        )
        assert ws.sent[0]["data"]["strategy"] == "least_loaded"
        assert ws.sent[0]["data"]["reason"] == "auto_handoff"
        assert "by_user_id" not in ws.sent[0]["data"]

    async def test_publish_operator_changed_rejects_invalid_reason(self):
        ws = FakeWebSocket()
        await inbox_ws.register_subscriber(7, ws, role="field_agent")
        n = await inbox_ws.publish_session_operator_changed(
            session_id=1, prev_operator_id=None, operator_id=2, reason="foo"
        )
        assert n == 0
        assert ws.sent == []

    async def test_publish_state_changed_envelope(self):
        ws = FakeWebSocket()
        await inbox_ws.register_subscriber(7, ws, role="field_agent")
        n = await inbox_ws.publish_session_state_changed(
            session_id=42,
            prev_state="active",
            state="closed",
            pedido_id=100,
        )
        assert n == 1
        p = ws.sent[0]
        assert p["event"] == "session.state_changed"
        assert p["data"] == {
            "session_id": 42,
            "prev_state": "active",
            "state": "closed",
            "pedido_id": 100,
        }

    async def test_publish_state_changed_with_mode(self):
        ws = FakeWebSocket()
        await inbox_ws.register_subscriber(7, ws, role="field_agent")
        await inbox_ws.publish_session_state_changed(
            session_id=1,
            prev_state="active",
            state="quote_sent",
            mode="whatsapp",
        )
        assert ws.sent[0]["data"]["mode"] == "whatsapp"

    async def test_publish_state_changed_noop_when_same(self):
        ws = FakeWebSocket()
        await inbox_ws.register_subscriber(7, ws, role="field_agent")
        n = await inbox_ws.publish_session_state_changed(
            session_id=1, prev_state="active", state="active"
        )
        assert n == 0
        assert ws.sent == []


class TestConcurrency:
    async def test_concurrent_register_unregister_no_race(self):
        async def add_remove(uid: int):
            ws = FakeWebSocket()
            await inbox_ws.register_subscriber(uid, ws, role="field_agent")
            await inbox_ws.unregister_subscriber(uid, ws)

        await asyncio.gather(*[add_remove(i % 3) for i in range(50)])
        assert inbox_ws.connected_users_count() == 0
        assert inbox_ws.total_sockets_count() == 0
