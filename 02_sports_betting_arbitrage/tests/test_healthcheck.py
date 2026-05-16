"""Tests for HealthcheckServer from arbitrage.healthcheck."""

from __future__ import annotations

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from arbitrage.healthcheck import HealthcheckServer


async def _make_client(state: dict) -> TestClient:
    """Create a TestClient for HealthcheckServer."""
    server = HealthcheckServer(state, port=0)
    server._app = web.Application()
    server._app.router.add_get("/healthz", server._handle_healthz)
    client = TestClient(TestServer(server._app))
    await client.start_server()
    return client


class TestHealthcheckServer:
    """Tests for HealthcheckServer."""

    async def test_healthz_returns_200_when_healthy(self) -> None:
        """Returns 200 with status ok when scanner is active."""
        state = {"scanner_active": True, "last_scan_ts": ""}
        client = await _make_client(state)
        try:
            resp = await client.get("/healthz")
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"
            assert data["scanner_active"] is True
            assert "uptime_sec" in data
        finally:
            await client.close()

    async def test_healthz_returns_503_when_scanner_stopped_by_error(self) -> None:
        """Returns 503 when scanner stopped due to error."""
        state = {"scanner_active": False, "last_scan_ts": "", "scanner_stopped_by_error": True}
        client = await _make_client(state)
        try:
            resp = await client.get("/healthz")
            assert resp.status == 503
            data = await resp.json()
            assert data["status"] == "degraded"
        finally:
            await client.close()

    async def test_healthz_returns_503_when_last_scan_stale(self) -> None:
        """Returns 503 when last scan timestamp is older than 5 minutes."""
        state = {"scanner_active": True, "last_scan_ts": "2020-01-01T00:00:00+00:00"}
        client = await _make_client(state)
        try:
            resp = await client.get("/healthz")
            assert resp.status == 503
            data = await resp.json()
            assert data["status"] == "degraded"
        finally:
            await client.close()

    async def test_healthz_json_content_type(self) -> None:
        """Response has application/json content type."""
        state = {"scanner_active": True, "last_scan_ts": ""}
        client = await _make_client(state)
        try:
            resp = await client.get("/healthz")
            assert "application/json" in resp.content_type
        finally:
            await client.close()
