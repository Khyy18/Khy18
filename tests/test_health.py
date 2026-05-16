"""Тесты health-check эндпоинта."""

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient

from health.server import create_health_app


@pytest.fixture
def health_app():
    """Создать тестовое приложение health."""
    return create_health_app()


@pytest.mark.asyncio
async def test_health_returns_200(aiohttp_client, health_app):
    """GET /health возвращает 200 и JSON с нужными полями."""
    client = await aiohttp_client(health_app)
    resp = await client.get("/health")
    assert resp.status == 200

    data = await resp.json()
    assert "status" in data
    assert "uptime_seconds" in data
    assert "db_ok" in data
    assert "redis_ok" in data
    assert "last_heartbeat" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_health_version(aiohttp_client, health_app):
    """Версия в ответе соответствует ожидаемой."""
    client = await aiohttp_client(health_app)
    resp = await client.get("/health")
    data = await resp.json()
    assert data["version"] == "2.1"


@pytest.mark.asyncio
async def test_health_uptime_positive(aiohttp_client, health_app):
    """uptime_seconds - положительное число."""
    client = await aiohttp_client(health_app)
    resp = await client.get("/health")
    data = await resp.json()
    assert data["uptime_seconds"] >= 0


@pytest.mark.asyncio
async def test_health_redis_ok_false_when_no_url(aiohttp_client, health_app, monkeypatch):
    """redis_ok = false когда REDIS_URL пустой."""
    monkeypatch.setattr("config.REDIS_URL", "")
    client = await aiohttp_client(health_app)
    resp = await client.get("/health")
    data = await resp.json()
    assert data["redis_ok"] is False


@pytest.mark.asyncio
async def test_health_status_field(aiohttp_client, health_app):
    """status принимает ожидаемые значения."""
    client = await aiohttp_client(health_app)
    resp = await client.get("/health")
    data = await resp.json()
    assert data["status"] in ("ok", "degraded")
