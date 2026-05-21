"""Тесты REST API эндпоинтов."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestHealth:
    """Тесты healthcheck."""

    async def test_health_returns_ok(self, client: AsyncClient):
        """Health endpoint возвращает 200."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("ok", "degraded")


@pytest.mark.asyncio
class TestProfile:
    """Тесты профиля пользователя."""

    async def test_profile_requires_auth(self, client: AsyncClient):
        """Профиль без токена отклоняется."""
        response = await client.get("/profile")
        assert response.status_code in (401, 403)

    async def test_profile_returns_user_data(self, client: AsyncClient, test_user):
        """Профиль возвращает данные пользователя."""
        user_id, token = test_user

        response = await client.get(
            "/profile",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == user_id
        assert data["balance"] == "100.00"


@pytest.mark.asyncio
class TestSessions:
    """Тесты списка сессий."""

    async def test_sessions_list_empty(self, client: AsyncClient, test_user):
        """Новый пользователь - пустой список сессий."""
        _, token = test_user

        response = await client.get(
            "/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.asyncio
class TestSubscriptions:
    """Тесты подписок."""

    async def test_plans_returns_list(self, client: AsyncClient):
        """Список планов доступен без авторизации."""
        response = await client.get("/subscriptions/plans")
        assert response.status_code == 200
        plans = response.json()
        assert len(plans) == 3
        plan_ids = [p["id"] for p in plans]
        assert "free" in plan_ids
        assert "basic" in plan_ids
        assert "premium" in plan_ids


@pytest.mark.asyncio
class TestAdmin:
    """Тесты административных эндпоинтов."""

    async def test_admin_stats_requires_key(self, client: AsyncClient):
        """Admin stats без ключа отклоняется."""
        response = await client.get("/admin/stats")
        assert response.status_code == 422  # Missing required header

    async def test_admin_stats_wrong_key(self, client: AsyncClient):
        """Admin stats с неправильным ключом отклоняется."""
        response = await client.get(
            "/admin/stats",
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert response.status_code in (403, 503)
