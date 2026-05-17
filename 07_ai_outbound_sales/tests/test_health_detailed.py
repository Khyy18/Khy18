"""Tests for the enhanced health check router."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from dashboard.routes.health import router, _check_stripe, _check_twilio, _check_deepgram, _check_elevenlabs


@pytest.fixture
def app_with_health_router():
    """Create a minimal FastAPI app with the health router for testing."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
async def client(app_with_health_router):
    """Async test client for the health router app."""
    transport = ASGITransport(app=app_with_health_router)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthDetailedEnhanced:
    """Tests for GET /health/detailed/enhanced endpoint."""

    async def test_all_healthy(self, client):
        """All services healthy returns 200 with overall_status=healthy."""
        with patch("dashboard.routes.health._check_postgres", new_callable=AsyncMock) as mock_pg, \
             patch("dashboard.routes.health._check_redis", new_callable=AsyncMock) as mock_redis, \
             patch("dashboard.routes.health._check_stripe") as mock_stripe, \
             patch("dashboard.routes.health._check_twilio") as mock_twilio, \
             patch("dashboard.routes.health._check_deepgram") as mock_deepgram, \
             patch("dashboard.routes.health._check_elevenlabs") as mock_eleven:
            mock_pg.return_value = {"status": "healthy", "detail": "connection OK"}
            mock_redis.return_value = {"status": "healthy", "detail": "PONG received"}
            mock_stripe.return_value = {"status": "healthy", "detail": "key format valid"}
            mock_twilio.return_value = {"status": "healthy", "detail": "SID format valid"}
            mock_deepgram.return_value = {"status": "healthy", "detail": "key present"}
            mock_eleven.return_value = {"status": "healthy", "detail": "key present"}

            resp = await client.get("/health/detailed/enhanced")
            assert resp.status_code == 200
            data = resp.json()
            assert data["overall_status"] == "healthy"
            assert "timestamp" in data
            assert len(data["services"]) == 6

    async def test_degraded_status(self, client):
        """If a service is degraded, overall status is degraded."""
        with patch("dashboard.routes.health._check_postgres", new_callable=AsyncMock) as mock_pg, \
             patch("dashboard.routes.health._check_redis", new_callable=AsyncMock) as mock_redis, \
             patch("dashboard.routes.health._check_stripe") as mock_stripe, \
             patch("dashboard.routes.health._check_twilio") as mock_twilio, \
             patch("dashboard.routes.health._check_deepgram") as mock_deepgram, \
             patch("dashboard.routes.health._check_elevenlabs") as mock_eleven:
            mock_pg.return_value = {"status": "healthy", "detail": "connection OK"}
            mock_redis.return_value = {"status": "healthy", "detail": "PONG received"}
            mock_stripe.return_value = {"status": "degraded", "detail": "key not configured"}
            mock_twilio.return_value = {"status": "healthy", "detail": "SID format valid"}
            mock_deepgram.return_value = {"status": "healthy", "detail": "key present"}
            mock_eleven.return_value = {"status": "healthy", "detail": "key present"}

            resp = await client.get("/health/detailed/enhanced")
            assert resp.status_code == 200
            data = resp.json()
            assert data["overall_status"] == "degraded"

    async def test_unhealthy_status(self, client):
        """If a critical service is unhealthy, overall status is unhealthy and returns 503."""
        with patch("dashboard.routes.health._check_postgres", new_callable=AsyncMock) as mock_pg, \
             patch("dashboard.routes.health._check_redis", new_callable=AsyncMock) as mock_redis, \
             patch("dashboard.routes.health._check_stripe") as mock_stripe, \
             patch("dashboard.routes.health._check_twilio") as mock_twilio, \
             patch("dashboard.routes.health._check_deepgram") as mock_deepgram, \
             patch("dashboard.routes.health._check_elevenlabs") as mock_eleven:
            mock_pg.return_value = {"status": "unhealthy", "detail": "connection refused"}
            mock_redis.return_value = {"status": "healthy", "detail": "PONG received"}
            mock_stripe.return_value = {"status": "healthy", "detail": "key format valid"}
            mock_twilio.return_value = {"status": "healthy", "detail": "SID format valid"}
            mock_deepgram.return_value = {"status": "healthy", "detail": "key present"}
            mock_eleven.return_value = {"status": "healthy", "detail": "key present"}

            resp = await client.get("/health/detailed/enhanced")
            assert resp.status_code == 503
            data = resp.json()
            assert data["overall_status"] == "unhealthy"

    async def test_services_included(self, client):
        """All expected services are present in the response."""
        with patch("dashboard.routes.health._check_postgres", new_callable=AsyncMock) as mock_pg, \
             patch("dashboard.routes.health._check_redis", new_callable=AsyncMock) as mock_redis, \
             patch("dashboard.routes.health._check_stripe") as mock_stripe, \
             patch("dashboard.routes.health._check_twilio") as mock_twilio, \
             patch("dashboard.routes.health._check_deepgram") as mock_deepgram, \
             patch("dashboard.routes.health._check_elevenlabs") as mock_eleven:
            mock_pg.return_value = {"status": "healthy", "detail": "OK"}
            mock_redis.return_value = {"status": "healthy", "detail": "OK"}
            mock_stripe.return_value = {"status": "healthy", "detail": "OK"}
            mock_twilio.return_value = {"status": "healthy", "detail": "OK"}
            mock_deepgram.return_value = {"status": "healthy", "detail": "OK"}
            mock_eleven.return_value = {"status": "healthy", "detail": "OK"}

            resp = await client.get("/health/detailed/enhanced")
            data = resp.json()
            expected_services = {"postgresql", "redis", "stripe", "twilio", "deepgram", "elevenlabs"}
            assert set(data["services"].keys()) == expected_services


class TestStripeCheck:
    """Tests for Stripe key format validation."""

    def test_stripe_valid_live_key(self):
        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_live_abc123"}):
            result = _check_stripe()
            assert result["status"] == "healthy"

    def test_stripe_valid_test_key(self):
        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_abc123"}):
            result = _check_stripe()
            assert result["status"] == "healthy"

    def test_stripe_missing_key(self):
        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": ""}, clear=False):
            result = _check_stripe()
            assert result["status"] == "degraded"

    def test_stripe_invalid_format(self):
        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "invalid_key"}):
            result = _check_stripe()
            assert result["status"] == "degraded"


class TestTwilioCheck:
    """Tests for Twilio SID format validation."""

    def test_twilio_valid_sid(self):
        with patch.dict(os.environ, {"TWILIO_ACCOUNT_SID": "AC" + "a" * 32}):
            result = _check_twilio()
            assert result["status"] == "healthy"

    def test_twilio_missing_sid(self):
        with patch.dict(os.environ, {"TWILIO_ACCOUNT_SID": ""}, clear=False):
            result = _check_twilio()
            assert result["status"] == "degraded"

    def test_twilio_invalid_format(self):
        with patch.dict(os.environ, {"TWILIO_ACCOUNT_SID": "INVALID123"}):
            result = _check_twilio()
            assert result["status"] == "degraded"


class TestDeepgramCheck:
    """Tests for Deepgram key presence check."""

    def test_deepgram_key_present(self):
        with patch.dict(os.environ, {"DEEPGRAM_API_KEY": "some-key-value"}):
            result = _check_deepgram()
            assert result["status"] == "healthy"

    def test_deepgram_key_missing(self):
        with patch.dict(os.environ, {"DEEPGRAM_API_KEY": ""}, clear=False):
            result = _check_deepgram()
            assert result["status"] == "degraded"


class TestElevenLabsCheck:
    """Tests for ElevenLabs key presence check."""

    def test_elevenlabs_key_present(self):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "some-key-value"}):
            result = _check_elevenlabs()
            assert result["status"] == "healthy"

    def test_elevenlabs_key_missing(self):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": ""}, clear=False):
            result = _check_elevenlabs()
            assert result["status"] == "degraded"
