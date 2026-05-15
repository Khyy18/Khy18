"""Tests for mini app API endpoints."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

import database
from api.app import app


@pytest_asyncio.fixture
async def api_client(initialized_db):
    """Create a test client with API key for authenticated requests."""
    from api.auth import create_api_key

    await database.get_or_create_client(telegram_id=9999, username="miniapp_test")
    api_key = await create_api_key(client_id=9999, rate_limit=100)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["X-API-Key"] = api_key
        yield client


@pytest.mark.asyncio
class TestMiniApp:
    """Tests for mini app API endpoints."""

    async def test_get_services(self, api_client):
        """GET /api/miniapp/services returns service list."""
        response = await api_client.get("/api/miniapp/services")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "name" in data[0]
        assert "price" in data[0]
        assert "type" in data[0]

    async def test_get_orders_empty(self, api_client):
        """GET /api/miniapp/orders/{telegram_id} returns empty list for new user."""
        response = await api_client.get("/api/miniapp/orders/9999")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_balance(self, api_client):
        """GET /api/miniapp/balance/{telegram_id} returns balance info."""
        response = await api_client.get("/api/miniapp/balance/9999")
        assert response.status_code == 200
        data = response.json()
        assert "balance" in data
        assert "total_spent" in data
        assert "order_count" in data

    async def test_create_order(self, api_client):
        """POST /api/miniapp/orders creates an order."""
        response = await api_client.post(
            "/api/miniapp/orders",
            json={
                "telegram_id": 9999,
                "service_type": "rewrite",
                "input_text": "Test text for mini app order",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "order_id" in data
        assert "price" in data
        assert data["status"] == "pending"

    async def test_create_order_invalid_service(self, api_client):
        """POST /api/miniapp/orders rejects invalid service type."""
        response = await api_client.post(
            "/api/miniapp/orders",
            json={
                "telegram_id": 9999,
                "service_type": "nonexistent_service",
                "input_text": "Test text",
            },
        )
        assert response.status_code == 400

    async def test_validate_init_data_empty(self, api_client):
        """POST /api/miniapp/validate-init-data returns invalid for empty data."""
        response = await api_client.post(
            "/api/miniapp/validate-init-data",
            json={"init_data": ""},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    async def test_validate_init_data_valid(self, api_client):
        """POST /api/miniapp/validate-init-data returns valid for data with = sign."""
        response = await api_client.post(
            "/api/miniapp/validate-init-data",
            json={"init_data": "user=123&hash=abc"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
