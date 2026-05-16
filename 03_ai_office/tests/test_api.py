"""Тесты FastAPI endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(test_client: AsyncClient):
    """Тест эндпоинта проверки здоровья."""
    response = await test_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_list_agents_empty(test_client: AsyncClient):
    """Тест получения пустого списка агентов."""
    response = await test_client.get("/api/agents")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_agents(test_client: AsyncClient, seed_data):
    """Тест получения списка агентов с данными."""
    response = await test_client.get("/api/agents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = [a["name"] for a in data]
    assert "Alice" in names
    assert "Sam" in names


@pytest.mark.asyncio
async def test_get_agent(test_client: AsyncClient, seed_data):
    """Тест получения одного агента по ID."""
    agents = seed_data["agents"]
    agent_id = agents[0].id
    response = await test_client.get(f"/api/agents/{agent_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Alice"
    assert data["role"] == "Персональный ассистент"


@pytest.mark.asyncio
async def test_get_agent_not_found(test_client: AsyncClient):
    """Тест получения несуществующего агента."""
    response = await test_client.get("/api/agents/999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_tasks(test_client: AsyncClient, seed_data):
    """Тест получения списка задач."""
    response = await test_client.get("/api/tasks")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_list_tasks_filter_status(test_client: AsyncClient, seed_data):
    """Тест фильтрации задач по статусу."""
    response = await test_client.get("/api/tasks?status=open")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "open"


@pytest.mark.asyncio
async def test_create_task(test_client: AsyncClient):
    """Тест создания задачи через API."""
    task_data = {
        "description": "Новая задача через API",
        "priority": "high",
    }
    response = await test_client.post("/api/tasks", json=task_data)
    assert response.status_code == 201
    data = response.json()
    assert data["description"] == "Новая задача через API"
    assert data["priority"] == "high"
    assert data["status"] == "open"
    assert data["creator_type"] == "user"


@pytest.mark.asyncio
async def test_update_task(test_client: AsyncClient, seed_data):
    """Тест обновления задачи."""
    tasks = seed_data["tasks"]
    task_id = tasks[0].id
    update_data = {"status": "closed"}
    response = await test_client.patch(f"/api/tasks/{task_id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "closed"


@pytest.mark.asyncio
async def test_update_task_not_found(test_client: AsyncClient):
    """Тест обновления несуществующей задачи."""
    update_data = {"status": "closed"}
    response = await test_client.patch("/api/tasks/999", json=update_data)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_activity(test_client: AsyncClient, seed_data):
    """Тест получения лога активности."""
    response = await test_client.get("/api/activity")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["limit"] == 20
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_list_activity_pagination(test_client: AsyncClient, seed_data):
    """Тест пагинации лога активности."""
    response = await test_client.get("/api/activity?limit=1&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 1
    assert data["limit"] == 1
    assert data["offset"] == 0
