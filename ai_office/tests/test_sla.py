"""Тесты SLAEngine - цели, обнаружение нарушений, статистика."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from ai_office.core.models import Agent, Task
from ai_office.core.sla import SLAEngine


@pytest.mark.asyncio
async def test_compute_sla_target_urgent():
    """Тест вычисления SLA для urgent приоритета."""
    engine = SLAEngine()
    target = await engine.compute_sla_target("urgent")
    assert target == 30


@pytest.mark.asyncio
async def test_compute_sla_target_high():
    """Тест вычисления SLA для high приоритета."""
    engine = SLAEngine()
    target = await engine.compute_sla_target("high")
    assert target == 120


@pytest.mark.asyncio
async def test_compute_sla_target_medium():
    """Тест вычисления SLA для medium приоритета."""
    engine = SLAEngine()
    target = await engine.compute_sla_target("medium")
    assert target == 300


@pytest.mark.asyncio
async def test_compute_sla_target_low():
    """Тест вычисления SLA для low приоритета."""
    engine = SLAEngine()
    target = await engine.compute_sla_target("low")
    assert target == 900


@pytest.mark.asyncio
async def test_compute_sla_target_unknown():
    """Тест вычисления SLA для неизвестного приоритета (default=300)."""
    engine = SLAEngine()
    target = await engine.compute_sla_target("critical")
    assert target == 300


@pytest.mark.asyncio
async def test_check_breaches_no_tasks(async_session):
    """Тест проверки нарушений при отсутствии задач."""
    engine = SLAEngine()
    breaches = await engine.check_breaches(async_session)
    assert breaches == []


@pytest.mark.asyncio
async def test_check_breaches_detects_breach(async_session):
    """Тест обнаружения нарушения SLA."""
    engine = SLAEngine()

    # Create a task that has breached its SLA
    task = Task(
        description="Urgent task breaching SLA",
        creator_type="user",
        creator_id="user_1",
        status="in_progress",
        priority="urgent",
        sla_target_seconds=30,
    )
    async_session.add(task)
    await async_session.commit()
    await async_session.refresh(task)

    # Manually set created_at to the past to simulate breach
    past_time = datetime.now(timezone.utc) - timedelta(seconds=60)
    task.created_at = past_time
    await async_session.commit()

    breaches = await engine.check_breaches(async_session)
    assert len(breaches) == 1
    assert breaches[0]["task_id"] == task.id
    assert breaches[0]["priority"] == "urgent"
    assert breaches[0]["breach_seconds"] > 0


@pytest.mark.asyncio
async def test_check_breaches_no_breach_within_target(async_session):
    """Тест: задача в пределах SLA не считается нарушением."""
    engine = SLAEngine()

    task = Task(
        description="Task within SLA",
        creator_type="user",
        creator_id="user_1",
        status="in_progress",
        priority="low",
        sla_target_seconds=900,
    )
    async_session.add(task)
    await async_session.commit()

    breaches = await engine.check_breaches(async_session)
    assert len(breaches) == 0


@pytest.mark.asyncio
async def test_get_sla_status_empty(async_session):
    """Тест статуса SLA при отсутствии задач с SLA."""
    engine = SLAEngine()
    status = await engine.get_sla_status(async_session)
    assert status["compliance_percent"] == 100.0
    assert status["breaches_count"] == 0
    assert status["avg_response_by_priority"] == {}


@pytest.mark.asyncio
async def test_get_sla_status_with_tasks(async_session):
    """Тест статуса SLA с задачами."""
    engine = SLAEngine()

    # Create a task within SLA
    task1 = Task(
        description="Task within SLA",
        creator_type="user",
        creator_id="user_1",
        status="in_progress",
        priority="low",
        sla_target_seconds=900,
    )
    async_session.add(task1)
    await async_session.commit()

    status = await engine.get_sla_status(async_session)
    assert status["compliance_percent"] == 100.0
    assert status["breaches_count"] == 0
    assert "low" in status["avg_response_by_priority"]
