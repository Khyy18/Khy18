"""API endpoint tests for backend."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestHealthCheck:
    """Tests for health check endpoints."""

    async def test_health_check(self, client: AsyncClient):
        """GET /health returns 200 with status ok."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_bot_health(self, client: AsyncClient):
        """GET /bot/health returns 200 with some status."""
        response = await client.get("/bot/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


class TestAuth:
    """Tests for authentication endpoints."""

    async def test_auth_telegram_invalid_data(self, client: AsyncClient):
        """POST /auth/telegram with garbage data returns 401."""
        response = await client.post(
            "/auth/telegram",
            json={"init_data": "garbage_invalid_data"},
        )
        assert response.status_code == 401

    async def test_auth_telegram_missing_user_id(self, client: AsyncClient):
        """POST /auth/telegram with init_data that has no user field returns 401."""
        response = await client.post(
            "/auth/telegram",
            json={"init_data": "query_id=AAHdF6IQAAAAAN0XohDhrOrc"},
        )
        assert response.status_code == 401

    async def test_auth_telegram_valid_init_data(self, client: AsyncClient):
        """POST /auth/telegram with valid user data returns token (dev mode)."""
        # In dev mode (no bot token), init_data with URL-encoded user JSON is accepted
        init_data = "user=%7B%22id%22%3A123456%2C%22username%22%3A%22test%22%7D"
        response = await client.post(
            "/auth/telegram",
            json={"init_data": init_data},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"


class TestDeals:
    """Tests for deals endpoints."""

    async def test_get_deals_unauthorized(self, client: AsyncClient):
        """GET /deals without auth returns 401."""
        response = await client.get("/deals")
        assert response.status_code == 401

    async def test_get_deals_empty(self, client: AsyncClient, auth_headers: dict):
        """GET /deals with auth returns empty list."""
        response = await client.get("/deals", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_get_deal_not_found(self, client: AsyncClient, auth_headers: dict):
        """GET /deals/99999 returns 404."""
        response = await client.get("/deals/99999", headers=auth_headers)
        assert response.status_code == 404


class TestAlerts:
    """Tests for alerts endpoints."""

    async def test_get_alerts_empty(self, client: AsyncClient, auth_headers: dict):
        """GET /alerts returns empty list for new user."""
        response = await client.get("/alerts", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    async def test_create_alert(self, client: AsyncClient, auth_headers: dict):
        """POST /alerts with valid data creates alert."""
        response = await client.post(
            "/alerts",
            json={"keyword": "iPhone 15", "max_price": 80000.0, "category": "electronics"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["keyword"] == "iPhone 15"
        assert data["max_price"] == 80000.0
        assert data["category"] == "electronics"
        assert data["is_active"] is True
        assert "id" in data

    async def test_delete_alert_not_found(self, client: AsyncClient, auth_headers: dict):
        """DELETE /alerts/99999 returns 404."""
        response = await client.delete("/alerts/99999", headers=auth_headers)
        assert response.status_code == 404
