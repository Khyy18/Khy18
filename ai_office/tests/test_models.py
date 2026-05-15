"""Тесты моделей базы данных."""

import pytest
from sqlalchemy import select

from ai_office.core.models import Agent, Task, ActivityLog


@pytest.mark.asyncio
async def test_create_agent(async_session):
    """Тест создания агента в БД."""
    agent = Agent(
        name="TestAgent",
        role="Тестовый агент",
        system_prompt="Ты тестовый агент.",
        status="idle",
    )
    async_session.add(agent)
    await async_session.commit()

    result = await async_session.execute(select(Agent).where(Agent.name == "TestAgent"))
    saved_agent = result.scalar_one()

    assert saved_agent.name == "TestAgent"
    assert saved_agent.role == "Тестовый агент"
    assert saved_agent.status == "idle"
    assert saved_agent.id is not None


@pytest.mark.asyncio
async def test_create_task(async_session):
    """Тест создания задачи в БД."""
    task = Task(
        description="Тестовая задача",
        creator_type="user",
        creator_id="test_user",
        status="open",
        priority="high",
    )
    async_session.add(task)
    await async_session.commit()

    result = await async_session.execute(select(Task).where(Task.description == "Тестовая задача"))
    saved_task = result.scalar_one()

    assert saved_task.description == "Тестовая задача"
    assert saved_task.creator_type == "user"
    assert saved_task.status == "open"
    assert saved_task.priority == "high"
    assert saved_task.id is not None


@pytest.mark.asyncio
async def test_create_activity_log(async_session):
    """Тест создания записи активности в БД."""
    # Сначала создаем агента
    agent = Agent(
        name="LogAgent",
        role="Агент для логов",
        system_prompt="Тест",
        status="idle",
    )
    async_session.add(agent)
    await async_session.flush()

    log = ActivityLog(
        agent_id=agent.id,
        action_type="test_action",
        action_description="Тестовое действие",
    )
    async_session.add(log)
    await async_session.commit()

    result = await async_session.execute(
        select(ActivityLog).where(ActivityLog.action_type == "test_action")
    )
    saved_log = result.scalar_one()

    assert saved_log.agent_id == agent.id
    assert saved_log.action_type == "test_action"
    assert saved_log.action_description == "Тестовое действие"
    assert saved_log.id is not None


@pytest.mark.asyncio
async def test_agent_activity_relationship(async_session):
    """Тест связи Agent -> ActivityLog."""
    agent = Agent(
        name="RelAgent",
        role="Агент",
        system_prompt="Тест",
        status="idle",
    )
    async_session.add(agent)
    await async_session.flush()

    log1 = ActivityLog(
        agent_id=agent.id,
        action_type="action_1",
        action_description="Действие 1",
    )
    log2 = ActivityLog(
        agent_id=agent.id,
        action_type="action_2",
        action_description="Действие 2",
    )
    async_session.add_all([log1, log2])
    await async_session.commit()

    # Перезагружаем агента
    result = await async_session.execute(select(Agent).where(Agent.name == "RelAgent"))
    loaded_agent = result.scalar_one()

    assert len(loaded_agent.activity_logs) == 2
