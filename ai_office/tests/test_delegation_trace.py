"""Тесты для трассировки делегирований."""

import json

import pytest
from httpx import AsyncClient

from ai_office.core.models import DelegationTrace, Task


@pytest.mark.asyncio
async def test_trace_model_creation(async_session):
    """Создание DelegationTrace в БД с проверкой полей."""
    task = Task(
        description="Test task",
        creator_type="agent",
        creator_id="test",
        status="open",
        priority="medium",
    )
    async_session.add(task)
    await async_session.flush()

    messages = [
        {"role": "system", "content": "System prompt", "timestamp": "2026-01-01T00:00:00"},
        {"role": "human", "content": "Task description", "timestamp": "2026-01-01T00:00:01"},
        {"role": "ai", "content": "Response", "timestamp": "2026-01-01T00:00:02"},
    ]

    trace = DelegationTrace(
        source_agent="delegation",
        target_agent="sam",
        task_id=task.id,
        messages_json=json.dumps(messages, ensure_ascii=False),
    )
    async_session.add(trace)
    await async_session.commit()

    assert trace.id is not None
    assert trace.source_agent == "delegation"
    assert trace.target_agent == "sam"
    assert trace.task_id == task.id

    parsed = json.loads(trace.messages_json)
    assert len(parsed) == 3
    assert parsed[0]["role"] == "system"


@pytest.mark.asyncio
async def test_get_trace_api(test_client: AsyncClient, async_session):
    """GET /api/delegations/{id}/trace возвращает трассировку."""
    task = Task(
        description="API test task",
        creator_type="agent",
        creator_id="test",
        status="open",
        priority="medium",
    )
    async_session.add(task)
    await async_session.flush()

    messages = [
        {"role": "human", "content": "Do something", "timestamp": "2026-01-01T00:00:00"},
        {"role": "ai", "content": "Done!", "timestamp": "2026-01-01T00:00:01"},
    ]

    trace = DelegationTrace(
        source_agent="delegation",
        target_agent="alice",
        task_id=task.id,
        messages_json=json.dumps(messages),
    )
    async_session.add(trace)
    await async_session.commit()

    response = await test_client.get(f"/api/delegations/{trace.id}/trace")
    assert response.status_code == 200
    data = response.json()
    assert data["source_agent"] == "delegation"
    assert data["target_agent"] == "alice"
    assert data["task_id"] == task.id
    assert len(data["messages"]) == 2
    assert data["messages"][0]["content"] == "Do something"


@pytest.mark.asyncio
async def test_get_trace_not_found(test_client: AsyncClient, async_session):
    """GET /api/delegations/999/trace возвращает 404."""
    response = await test_client.get("/api/delegations/999/trace")
    assert response.status_code == 404
