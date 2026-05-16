"""Тесты API дашборда."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta

from ai_office.core.models import ActivityLog, Agent, Task, TokenUsage


@pytest.mark.asyncio
async def test_dashboard_returns_200(test_client):
    """GET /api/dashboard returns 200 with correct schema fields."""
    response = await test_client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()

    assert "tasks_today" in data
    assert "tasks_week_history" in data
    assert "cost_today" in data
    assert "cost_week_history" in data
    assert "avg_response_ms" in data
    assert "response_time_history" in data
    assert "active_agents" in data
    assert "hourly_activity" in data

    assert isinstance(data["tasks_today"], int)
    assert isinstance(data["tasks_week_history"], list)
    assert len(data["tasks_week_history"]) == 7
    assert isinstance(data["cost_today"], float)
    assert isinstance(data["cost_week_history"], list)
    assert len(data["cost_week_history"]) == 7
    assert isinstance(data["avg_response_ms"], int)
    assert isinstance(data["response_time_history"], list)
    assert len(data["response_time_history"]) == 7
    assert isinstance(data["active_agents"], int)
    assert isinstance(data["hourly_activity"], list)
    assert len(data["hourly_activity"]) == 24


@pytest.mark.asyncio
async def test_dashboard_with_seeded_data(test_client, async_session):
    """Dashboard returns non-zero values when data is seeded."""
    # Seed agent
    agent = Agent(
        name="Alice",
        role="PM",
        system_prompt="Test prompt",
        status="working",
    )
    async_session.add(agent)
    await async_session.flush()

    # Seed task created today
    task = Task(
        description="Test task for dashboard",
        creator_type="user",
        creator_id="test_user",
        executor_id=agent.id,
        status="open",
        priority="high",
    )
    async_session.add(task)

    # Seed token usage today
    usage = TokenUsage(
        provider="openai",
        model="gpt-4",
        prompt_tokens=100,
        completion_tokens=50,
        estimated_cost_usd=0.05,
        agent_name="Alice",
    )
    async_session.add(usage)

    # Seed activity log (recent)
    log = ActivityLog(
        agent_id=agent.id,
        action_type="task_started",
        action_description="Started working on test task",
    )
    async_session.add(log)
    await async_session.commit()

    response = await test_client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()

    assert data["tasks_today"] >= 1
    assert data["cost_today"] >= 0.05
    assert data["active_agents"] >= 1
