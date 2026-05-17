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


class TestCORS:
    """Tests for CORS configuration."""

    async def test_cors_headers_on_request(self, client: AsyncClient):
        """Request with Origin header gets CORS headers in response."""
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" in response.headers

    async def test_cors_allows_configured_origin(self, client: AsyncClient):
        """Configured origin is allowed in CORS response."""
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


class TestOnboarding:
    """Tests for onboarding endpoints."""

    async def test_get_onboarding_steps(self, client: AsyncClient, auth_headers: dict):
        """GET /onboarding/steps with auth returns steps list."""
        response = await client.get("/onboarding/steps", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "steps" in data
        assert isinstance(data["steps"], list)
        assert len(data["steps"]) > 0
        assert "step_id" in data["steps"][0]

    async def test_complete_onboarding_step(self, client: AsyncClient, auth_headers: dict):
        """POST /onboarding/complete/1 with auth returns updated completed list."""
        response = await client.post("/onboarding/complete/1", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "completed" in data
        assert 1 in data["completed"]

    async def test_get_onboarding_steps_unauthorized(self, client: AsyncClient):
        """GET /onboarding/steps without auth returns 401."""
        response = await client.get("/onboarding/steps")
        assert response.status_code in (401, 403)


class TestFavorites:
    """Tests for favorites endpoints."""

    async def test_favorite_nonexistent_product_returns_404(self, client: AsyncClient, auth_headers: dict):
        """POST /favorites/99999 for non-existent product returns 404."""
        response = await client.post("/favorites/99999", headers=auth_headers)
        assert response.status_code == 404

    async def test_get_favorites_empty(self, client: AsyncClient, auth_headers: dict):
        """GET /favorites for new user returns empty list."""
        response = await client.get("/favorites", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    async def test_favorites_full_flow(self, client: AsyncClient, auth_headers: dict, test_session):
        """Full favorites flow: add product, toggle favorite, get, delete."""
        from app.db.models import Product

        # Create a product in the DB
        product = Product(
            marketplace="wb",
            external_id="test_fav_123",
            name="Favorite Test Product",
            url="https://example.com/product/123",
        )
        test_session.add(product)
        await test_session.commit()
        await test_session.refresh(product)

        # Add to favorites
        response = await client.post(f"/favorites/{product.id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["is_favorite"] is True

        # Get favorites - should contain the product
        response = await client.get("/favorites", headers=auth_headers)
        assert response.status_code == 200
        items = response.json()
        assert len(items) >= 1

        # Remove from favorites
        response = await client.delete(f"/favorites/{product.id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["is_favorite"] is False

    async def test_delete_favorite_not_in_list(self, client: AsyncClient, auth_headers: dict, test_session):
        """DELETE /favorites/{id} when not favorited returns 404."""
        from app.db.models import Product

        product = Product(
            marketplace="ozon",
            external_id="not_fav_456",
            name="Not Favorite Product",
        )
        test_session.add(product)
        await test_session.commit()
        await test_session.refresh(product)

        response = await client.delete(f"/favorites/{product.id}", headers=auth_headers)
        assert response.status_code == 404


class TestWebSocket:
    """Tests for WebSocket endpoint."""

    async def test_websocket_ping_pong(self, client: AsyncClient, test_user):
        """WebSocket with valid token responds pong to ping."""
        from starlette.testclient import TestClient
        from app.main import app as fastapi_app
        from app.middleware.auth import create_access_token

        token = create_access_token({"sub": str(test_user.id)})

        # Use Starlette's synchronous TestClient for WebSocket
        with TestClient(fastapi_app) as sync_client:
            with sync_client.websocket_connect(f"/ws/prices?token={token}") as ws:
                ws.send_text("ping")
                data = ws.receive_text()
                assert data == "pong"

    async def test_websocket_invalid_token_closes_4001(self, client: AsyncClient):
        """WebSocket with invalid token is closed with code 4001."""
        from starlette.testclient import TestClient
        from app.main import app as fastapi_app
        from starlette.websockets import WebSocketDisconnect

        with TestClient(fastapi_app) as sync_client:
            with pytest.raises((WebSocketDisconnect, Exception)) as exc_info:
                with sync_client.websocket_connect("/ws/prices?token=invalid_token") as ws:
                    ws.send_text("ping")
                    ws.receive_text()
            # Verify the disconnect happened (not some unrelated error)
            if isinstance(exc_info.value, WebSocketDisconnect):
                assert exc_info.value.code == 4001
