"""Тесты для API шаблонов задач."""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from ai_office.core.models import Agent, TaskTemplate


@pytest.mark.asyncio
async def test_get_templates(test_client: AsyncClient, async_session):
    """GET /api/templates возвращает 200 и заполняет шаблоны при первом вызове."""
    response = await test_client.get("/api/templates")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 8
    names = [t["name"] for t in data]
    assert "Code Review" in names
    assert "Bug Fix" in names
    assert "Deploy to Production" in names


@pytest.mark.asyncio
async def test_create_from_template(test_client: AsyncClient, async_session):
    """POST /api/tasks/from-template/{id} создает задачу из шаблона."""
    # Seed templates via GET
    response = await test_client.get("/api/templates")
    assert response.status_code == 200
    templates = response.json()
    template_id = templates[0]["id"]

    # Create task from template
    response = await test_client.post(f"/api/tasks/from-template/{template_id}")
    assert response.status_code == 201
    data = response.json()
    assert data["description"] == templates[0]["description_template"]
    assert data["priority"] == templates[0]["default_priority"]
    assert data["status"] == "open"


@pytest.mark.asyncio
async def test_create_from_template_not_found(test_client: AsyncClient, async_session):
    """POST /api/tasks/from-template/999 возвращает 404."""
    response = await test_client.post("/api/tasks/from-template/999")
    assert response.status_code == 404
