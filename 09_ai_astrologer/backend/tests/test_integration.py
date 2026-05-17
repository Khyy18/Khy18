"""Integration tests for the full AI Astrologer flow."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class FakeRedis:
    """Fake Redis for integration testing.

    Implements the subset of Redis commands used by the application:
    session store (get/set/delete), billing (eval/publish), rate limiter (pipeline).
    """

    def __init__(self):
        self._store = {}

    async def get(self, key):
        return self._store.get(key)

    async def set(self, key, value, ex=None):
        self._store[key] = value

    async def delete(self, key):
        self._store.pop(key, None)

    async def eval(self, script, numkeys, *args):
        """Simulate Lua script for atomic deduct."""
        key = args[0]
        cost = int(args[1])
        current = int(self._store.get(key) or "0")
        if current < cost:
            return [0, current]
        new_balance = current - cost
        self._store[key] = str(new_balance)
        return [1, new_balance]

    async def publish(self, channel, message):
        return 1

    async def zadd(self, key, mapping):
        if key not in self._store or not isinstance(self._store.get(key), dict):
            self._store[key] = {}
        self._store[key].update(mapping)

    async def zrem(self, key, *members):
        if key in self._store and isinstance(self._store[key], dict):
            for m in members:
                self._store[key].pop(m, None)

    async def zrangebyscore(self, key, min_s, max_s):
        return []

    async def zscore(self, key, member):
        return None

    async def zremrangebyscore(self, key, min_score, max_score):
        return 0

    async def zcard(self, key):
        if key in self._store and isinstance(self._store[key], dict):
            return len(self._store[key])
        return 0

    async def expire(self, key, seconds):
        pass

    def pipeline(self):
        """Return a fake pipeline that collects commands and executes them."""
        return FakePipeline(self)

    def pubsub(self):
        ps = AsyncMock()
        ps.subscribe = AsyncMock()
        return ps

    async def close(self):
        pass


class FakePipeline:
    """Fake Redis pipeline for rate limiter support."""

    def __init__(self, redis: FakeRedis):
        self._redis = redis
        self._commands = []

    def zremrangebyscore(self, key, min_score, max_score):
        self._commands.append(("zremrangebyscore", key, min_score, max_score))
        return self

    def zcard(self, key):
        self._commands.append(("zcard", key))
        return self

    def zadd(self, key, mapping):
        self._commands.append(("zadd", key, mapping))
        return self

    def expire(self, key, seconds):
        self._commands.append(("expire", key, seconds))
        return self

    async def execute(self):
        results = []
        for cmd in self._commands:
            if cmd[0] == "zremrangebyscore":
                results.append(0)
            elif cmd[0] == "zcard":
                key = cmd[1]
                if key in self._redis._store and isinstance(self._redis._store[key], dict):
                    results.append(len(self._redis._store[key]))
                else:
                    results.append(0)
            elif cmd[0] == "zadd":
                key, mapping = cmd[1], cmd[2]
                if key not in self._redis._store or not isinstance(self._redis._store.get(key), dict):
                    self._redis._store[key] = {}
                self._redis._store[key].update(mapping)
                results.append(1)
            elif cmd[0] == "expire":
                results.append(True)
        self._commands = []
        return results


@pytest.fixture
def fake_redis():
    """Create a FakeRedis instance for testing."""
    return FakeRedis()


@pytest.fixture
def client(fake_redis):
    """Create a FastAPI TestClient with mocked Redis and database.

    Patches Redis, database init, and Prometheus instrumentator to avoid
    middleware conflicts when the app instance is reused across tests.
    """
    mock_instrumentator = MagicMock()
    mock_instrumentator.instrument = MagicMock(return_value=mock_instrumentator)
    mock_instrumentator.expose = MagicMock(return_value=mock_instrumentator)

    with patch("redis.asyncio.from_url", return_value=fake_redis):
        with patch("app.database.init_database", new_callable=AsyncMock, return_value=None):
            with patch("app.main.create_instrumentator", return_value=mock_instrumentator):
                from app.main import app

                with TestClient(app) as c:
                    yield c


def _session_start_payload(user_id="tg_12345", balance=100):
    """Helper to build a session start payload."""
    return {
        "user_id": user_id,
        "birth_data": {
            "date": "1995-03-15",
            "time": "14:30",
            "lat": 55.7558,
            "lon": 37.6173,
            "city": "Moscow",
            "tz_offset": 3.0,
        },
        "balance": balance,
    }


class TestHealthCheck:
    """Tests for the health check endpoint."""

    def test_health_check(self, client):
        """Test GET /health returns ok status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "ai-astrologer"


class TestSessionFlow:
    """Tests for the session creation and status flow."""

    def test_create_session(self, client):
        """Test POST /api/session/start creates a session and returns expected fields."""
        response = client.post("/api/session/start", json=_session_start_payload())
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "natal_chart" in data
        assert "token" in data
        assert data["balance"] == 100
        # Natal chart should contain planet data
        assert "planets" in data["natal_chart"]
        assert len(data["natal_chart"]["planets"]) > 0

    def test_session_status(self, client):
        """Test session creation then status retrieval."""
        # Create session
        res = client.post("/api/session/start", json=_session_start_payload(user_id="tg_99"))
        assert res.status_code == 200
        session_id = res.json()["session_id"]

        # Get status
        status_res = client.get(f"/api/session/{session_id}/status")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["session_id"] == session_id
        assert status_data["user_id"] == "tg_99"
        assert status_data["balance"] == 100

    def test_session_not_found(self, client):
        """Test GET /api/session/{id}/status returns 404 for unknown session."""
        response = client.get("/api/session/nonexistent-id/status")
        assert response.status_code == 404


class TestWebSocketCallAuth:
    """Tests for WebSocket call endpoint authentication."""

    def test_websocket_call_valid_auth(self, client):
        """Test WebSocket call endpoint accepts valid auth token."""
        # Create a session to get session_id and token
        res = client.post("/api/session/start", json=_session_start_payload(
            user_id="tg_ws_test", balance=200
        ))
        assert res.status_code == 200
        session_id = res.json()["session_id"]
        token = res.json()["token"]

        # Connect to call WebSocket and authenticate
        with client.websocket_connect(f"/ws/call/{session_id}") as ws:
            # Send auth message
            ws.send_json({"type": "auth", "token": token})
            # After auth, server sends LISTENING state
            msg = ws.receive_json()
            assert msg["type"] == "pipeline_state"
            assert msg["state"] == "LISTENING"

    def test_websocket_call_invalid_auth(self, client):
        """Test WebSocket rejects invalid auth token with close code 4001."""
        res = client.post("/api/session/start", json=_session_start_payload(
            user_id="tg_bad_auth"
        ))
        session_id = res.json()["session_id"]

        with pytest.raises(Exception):
            with client.websocket_connect(f"/ws/call/{session_id}") as ws:
                ws.send_json({"type": "auth", "token": "wrong-token"})
                # Server should close with 4001 - reading will raise
                ws.receive_json()

    def test_websocket_call_session_not_found(self, client):
        """Test WebSocket for nonexistent session closes with 4004."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/call/nonexistent-session") as ws:
                ws.receive_json()

    def test_websocket_call_audio_processing(self, client):
        """Test WebSocket call handles audio bytes after auth."""
        res = client.post("/api/session/start", json=_session_start_payload(
            user_id="tg_audio_test", balance=200
        ))
        session_id = res.json()["session_id"]
        token = res.json()["token"]

        with client.websocket_connect(f"/ws/call/{session_id}") as ws:
            ws.send_json({"type": "auth", "token": token})
            # Receive LISTENING state
            msg = ws.receive_json()
            assert msg["type"] == "pipeline_state"
            assert msg["state"] == "LISTENING"

            # Send mock audio bytes - the VAD will buffer these
            # since they are zeros (silence), no utterance will be detected
            ws.send_bytes(b"\x00" * 4096)
            # Send more audio - still silence, VAD won't trigger
            ws.send_bytes(b"\x00" * 4096)
            # Connection remains open and server continues to listen


class TestWebSocketBillingAuth:
    """Tests for WebSocket billing endpoint authentication."""

    def test_websocket_billing_valid_auth(self, client):
        """Test WebSocket billing endpoint accepts valid auth token."""
        res = client.post("/api/session/start", json=_session_start_payload(
            user_id="tg_billing_test", balance=100
        ))
        session_id = res.json()["session_id"]
        token = res.json()["token"]

        with client.websocket_connect(f"/ws/billing/{session_id}") as ws:
            ws.send_json({"type": "auth", "token": token})
            # Billing loop starts - connection is established without error
            # We just verify the connection is accepted and stays open briefly

    def test_websocket_billing_invalid_auth(self, client):
        """Test WebSocket billing rejects invalid auth token."""
        res = client.post("/api/session/start", json=_session_start_payload(
            user_id="tg_billing_bad"
        ))
        session_id = res.json()["session_id"]

        with pytest.raises(Exception):
            with client.websocket_connect(f"/ws/billing/{session_id}") as ws:
                ws.send_json({"type": "auth", "token": "invalid-token"})
                ws.receive_json()

    def test_websocket_billing_session_not_found(self, client):
        """Test WebSocket billing for nonexistent session closes with 4004."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/billing/nonexistent-session") as ws:
                ws.receive_json()
