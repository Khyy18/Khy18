"""Тесты новых API endpoints (agent activity, agent tasks, plans, delegations)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.models import ActivityLog, Plan, PlanStep


@pytest.mark.asyncio
async def test_get_agent_activity(test_client: AsyncClient, seed_data):
    """Тест получения активности конкретного агента."""
    agents = seed_data["agents"]
    alice_id = agents[0].id

    response = await test_client.get(f"/api/agents/{alice_id}/activity")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    for item in data["items"]:
        assert item["agent_id"] == alice_id


@pytest.mark.asyncio
async def test_get_agent_activity_pagination(test_client: AsyncClient, seed_data):
    """Тест пагинации активности агента."""
    agents = seed_data["agents"]
    alice_id = agents[0].id

    response = await test_client.get(f"/api/agents/{alice_id}/activity?limit=1&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 1
    assert data["offset"] == 0
    assert len(data["items"]) <= 1


@pytest.mark.asyncio
async def test_get_agent_activity_not_found(test_client: AsyncClient):
    """Тест получения активности несуществующего агента."""
    response = await test_client.get("/api/agents/999/activity")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_agent_tasks(test_client: AsyncClient, seed_data):
    """Тест получения задач конкретного агента."""
    agents = seed_data["agents"]
    alice_id = agents[0].id

    response = await test_client.get(f"/api/agents/{alice_id}/tasks")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    for task in data:
        assert task["executor_id"] == alice_id


@pytest.mark.asyncio
async def test_get_agent_tasks_not_found(test_client: AsyncClient):
    """Тест получения задач несуществующего агента."""
    response = await test_client.get("/api/agents/999/tasks")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_plans_empty(test_client: AsyncClient):
    """Тест получения пустого списка планов."""
    response = await test_client.get("/api/plans")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_plans_with_data(test_client: AsyncClient, async_session: AsyncSession):
    """Тест получения списка планов с данными."""
    plan = Plan(goal="Разработать новую фичу", status="active")
    async_session.add(plan)
    await async_session.flush()

    step1 = PlanStep(
        plan_id=plan.id,
        step_number=1,
        description="Анализ требований",
        status="completed",
    )
    step2 = PlanStep(
        plan_id=plan.id,
        step_number=2,
        description="Реализация",
        status="pending",
    )
    async_session.add_all([step1, step2])
    await async_session.commit()

    response = await test_client.get("/api/plans")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["goal"] == "Разработать новую фичу"
    assert len(data[0]["steps"]) == 2


@pytest.mark.asyncio
async def test_get_plan_by_id(test_client: AsyncClient, async_session: AsyncSession):
    """Тест получения плана по ID."""
    plan = Plan(goal="Тестовый план", status="active")
    async_session.add(plan)
    await async_session.flush()

    step = PlanStep(
        plan_id=plan.id,
        step_number=1,
        description="Шаг 1",
        status="pending",
    )
    async_session.add(step)
    await async_session.commit()

    response = await test_client.get(f"/api/plans/{plan.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["goal"] == "Тестовый план"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["description"] == "Шаг 1"


@pytest.mark.asyncio
async def test_get_plan_not_found(test_client: AsyncClient):
    """Тест получения несуществующего плана."""
    response = await test_client.get("/api/plans/999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_delegations_empty(test_client: AsyncClient):
    """Тест получения пустого списка делегирований."""
    response = await test_client.get("/api/delegations")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_delegations_with_data(test_client: AsyncClient, seed_data, async_session: AsyncSession):
    """Тест получения делегирований с данными."""
    agents = seed_data["agents"]
    alice_id = agents[0].id

    delegation_log = ActivityLog(
        agent_id=alice_id,
        action_type="task_delegated",
        action_description="Делегирована задача: Исправить баг в API агенту Sam",
    )
    async_session.add(delegation_log)
    await async_session.commit()

    response = await test_client.get("/api/delegations")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    found = any(d["action_type"] == "task_delegated" for d in data)
    assert found
    # Проверяем что agent_name заполнен
    for d in data:
        assert d["agent_name"] is not None
