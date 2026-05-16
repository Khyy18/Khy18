"""Tests for proactive scheduler and scheduled tasks."""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai_office.core.database import Base
from ai_office.core.models import Agent, Task, ActivityLog
from ai_office.core.scheduler import Scheduler, ScheduledTask


# --- Scheduler unit tests ---


class TestScheduledTask:
    """Tests for ScheduledTask timing calculations."""

    def test_interval_hours(self):
        """Task with interval_hours returns correct seconds."""
        task = ScheduledTask(
            name="test",
            coro_factory=AsyncMock(),
            interval_hours=2,
        )
        assert task.seconds_until_next_run() == 7200

    def test_interval_hours_fractional(self):
        """Task with fractional interval_hours."""
        task = ScheduledTask(
            name="test",
            coro_factory=AsyncMock(),
            interval_hours=0.5,
        )
        assert task.seconds_until_next_run() == 1800

    def test_daily_hour_returns_positive(self):
        """Task with specific hour always returns positive seconds."""
        task = ScheduledTask(
            name="test",
            coro_factory=AsyncMock(),
            hour=10,
            minute=0,
        )
        result = task.seconds_until_next_run()
        assert result > 0
        assert result <= 86400  # Max 24 hours

    def test_weekly_returns_positive(self):
        """Task with day_of_week always returns positive seconds."""
        task = ScheduledTask(
            name="test",
            coro_factory=AsyncMock(),
            hour=10,
            minute=0,
            day_of_week="monday",
        )
        result = task.seconds_until_next_run()
        assert result > 0
        assert result <= 604800  # Max 7 days


class TestScheduler:
    """Tests for Scheduler class."""

    def test_register_task(self):
        """Registering a task adds it to the scheduler."""
        sched = Scheduler()
        sched.register_task(
            name="test_task",
            coro_factory=AsyncMock(),
            interval_hours=1,
        )
        assert len(sched.registered_tasks) == 1
        assert sched.registered_tasks[0].name == "test_task"

    def test_register_multiple_tasks(self):
        """Multiple tasks can be registered."""
        sched = Scheduler()
        sched.register_task(name="t1", coro_factory=AsyncMock(), interval_hours=1)
        sched.register_task(name="t2", coro_factory=AsyncMock(), hour=9)
        sched.register_task(name="t3", coro_factory=AsyncMock(), day_of_week="monday", hour=10)
        assert len(sched.registered_tasks) == 3

    @pytest.mark.asyncio
    async def test_start_disabled(self):
        """Scheduler does nothing when enable_proactive is False."""
        sched = Scheduler()
        sched.register_task(name="t1", coro_factory=AsyncMock(), interval_hours=1)

        with patch("ai_office.core.scheduler.settings") as mock_settings:
            mock_settings.enable_proactive = False
            await sched.start()
            assert not sched.is_started

    @pytest.mark.asyncio
    async def test_start_enabled(self):
        """Scheduler starts tasks when enable_proactive is True."""
        sched = Scheduler()
        mock_factory = AsyncMock()
        sched.register_task(name="t1", coro_factory=mock_factory, interval_hours=1)

        shutdown = asyncio.Event()

        with patch("ai_office.core.scheduler.settings") as mock_settings:
            mock_settings.enable_proactive = True
            await sched.start(shutdown_event=shutdown)
            assert sched.is_started
            # Clean up
            shutdown.set()
            await sched.stop()
            assert not sched.is_started

    @pytest.mark.asyncio
    async def test_task_executes(self):
        """Task factory is called after sleep."""
        sched = Scheduler()
        executed = asyncio.Event()

        async def mock_task():
            executed.set()

        sched.register_task(name="quick", coro_factory=mock_task, interval_hours=0.0001)

        shutdown = asyncio.Event()
        with patch("ai_office.core.scheduler.settings") as mock_settings:
            mock_settings.enable_proactive = True
            await sched.start(shutdown_event=shutdown)

            # Wait for task execution (with timeout)
            try:
                await asyncio.wait_for(executed.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

            shutdown.set()
            await sched.stop()

        assert executed.is_set()

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks(self):
        """Stopping the scheduler cancels all running task loops."""
        sched = Scheduler()
        sched.register_task(name="t1", coro_factory=AsyncMock(), interval_hours=24)

        with patch("ai_office.core.scheduler.settings") as mock_settings:
            mock_settings.enable_proactive = True
            await sched.start()
            assert len(sched._running_tasks) == 1
            await sched.stop()
            assert len(sched._running_tasks) == 0


# --- Proactive task tests ---


@pytest_asyncio.fixture
async def proactive_session():
    """Fixture providing an in-memory DB session with test data for proactive tasks."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        # Create agents
        alice = Agent(name="Alice", role="PM", system_prompt="", status="idle")
        eva = Agent(name="Eva", role="Analyst", system_prompt="", status="idle")
        leo = Agent(name="Leo", role="QA", system_prompt="", status="idle")
        nova = Agent(name="Nova", role="DevOps", system_prompt="", status="idle")
        session.add_all([alice, eva, leo, nova])
        await session.flush()

        # Create tasks - some overdue
        old_time = datetime.now(timezone.utc) - timedelta(hours=48)
        task1 = Task(
            description="Old task 1",
            creator_type="user",
            creator_id="user1",
            status="open",
            priority="high",
            created_at=old_time,
        )
        task2 = Task(
            description="Recent task",
            creator_type="user",
            creator_id="user1",
            status="in_progress",
            priority="medium",
        )
        task3 = Task(
            description="Done task",
            creator_type="user",
            creator_id="user1",
            status="done",
            priority="low",
            closed_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        session.add_all([task1, task2, task3])
        await session.commit()

        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_alice_standup(proactive_session):
    """Alice standup queries tasks and formats output correctly."""
    with patch("ai_office.core.proactive_tasks.async_session") as mock_session_ctx, \
         patch("ai_office.core.proactive_tasks.send_to_chat") as mock_send:
        mock_send.return_value = None

        # Make async_session return our test session
        class FakeCtx:
            async def __aenter__(self):
                return proactive_session
            async def __aexit__(self, *args):
                pass

        mock_session_ctx.return_value = FakeCtx()

        from ai_office.core.proactive_tasks import alice_daily_standup
        await alice_daily_standup()

        # Verify send was called
        mock_send.assert_called_once()
        message = mock_send.call_args[0][0]
        assert "стендап" in message.lower() or "Стендап" in message
        assert "Old task 1" in message or "Открытых задач" in message


@pytest.mark.asyncio
async def test_eva_weekly_report(proactive_session):
    """Eva weekly report queries and formats analytics."""
    with patch("ai_office.core.proactive_tasks.async_session") as mock_session_ctx, \
         patch("ai_office.core.proactive_tasks.send_to_chat") as mock_send:
        mock_send.return_value = None

        class FakeCtx:
            async def __aenter__(self):
                return proactive_session
            async def __aexit__(self, *args):
                pass

        mock_session_ctx.return_value = FakeCtx()

        from ai_office.core.proactive_tasks import eva_weekly_report
        await eva_weekly_report()

        mock_send.assert_called_once()
        message = mock_send.call_args[0][0]
        assert "отчёт" in message.lower() or "Отчёт" in message


@pytest.mark.asyncio
async def test_leo_overdue_alert(proactive_session):
    """Leo finds overdue tasks and sends alert."""
    with patch("ai_office.core.proactive_tasks.async_session") as mock_session_ctx, \
         patch("ai_office.core.proactive_tasks.send_to_chat") as mock_send:
        mock_send.return_value = None

        class FakeCtx:
            async def __aenter__(self):
                return proactive_session
            async def __aexit__(self, *args):
                pass

        mock_session_ctx.return_value = FakeCtx()

        from ai_office.core.proactive_tasks import leo_overdue_alert
        await leo_overdue_alert()

        # Should send alert because we have a task older than 24h
        mock_send.assert_called_once()
        message = mock_send.call_args[0][0]
        assert "Алерт" in message or "просроченных" in message


@pytest.mark.asyncio
async def test_leo_no_overdue(proactive_session):
    """Leo does not send alert when no overdue tasks exist."""
    # Remove the old task to have no overdue
    result = await proactive_session.execute(
        select(Task).where(Task.description == "Old task 1")
    )
    old_task = result.scalar_one()
    old_task.created_at = datetime.now(timezone.utc)
    await proactive_session.commit()

    with patch("ai_office.core.proactive_tasks.async_session") as mock_session_ctx, \
         patch("ai_office.core.proactive_tasks.send_to_chat") as mock_send:
        mock_send.return_value = None

        class FakeCtx:
            async def __aenter__(self):
                return proactive_session
            async def __aexit__(self, *args):
                pass

        mock_session_ctx.return_value = FakeCtx()

        from ai_office.core.proactive_tasks import leo_overdue_alert
        await leo_overdue_alert()

        # Should NOT send because no overdue tasks
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_nova_health_check_ok(proactive_session):
    """Nova health check does not send to Telegram when all is OK."""
    with patch("ai_office.core.proactive_tasks.async_session") as mock_session_ctx, \
         patch("ai_office.core.proactive_tasks.send_to_chat") as mock_send, \
         patch("ai_office.core.proactive_tasks.psutil") as mock_psutil:
        mock_send.return_value = None

        # Mock healthy system
        mock_psutil.virtual_memory.return_value = MagicMock(percent=50)
        mock_psutil.cpu_percent.return_value = 30

        class FakeCtx:
            async def __aenter__(self):
                return proactive_session
            async def __aexit__(self, *args):
                pass

        mock_session_ctx.return_value = FakeCtx()

        from ai_office.core.proactive_tasks import nova_health_check
        await nova_health_check()

        # Should NOT send message when all is OK
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_nova_health_check_high_memory(proactive_session):
    """Nova sends alert when memory is above 90%."""
    with patch("ai_office.core.proactive_tasks.async_session") as mock_session_ctx, \
         patch("ai_office.core.proactive_tasks.send_to_chat") as mock_send, \
         patch("ai_office.core.proactive_tasks.psutil") as mock_psutil:
        mock_send.return_value = None

        # Mock high memory usage
        mock_psutil.virtual_memory.return_value = MagicMock(percent=95)
        mock_psutil.cpu_percent.return_value = 30

        class FakeCtx:
            async def __aenter__(self):
                return proactive_session
            async def __aexit__(self, *args):
                pass

        mock_session_ctx.return_value = FakeCtx()

        from ai_office.core.proactive_tasks import nova_health_check
        await nova_health_check()

        # Should send alert for high memory
        mock_send.assert_called_once()
        message = mock_send.call_args[0][0]
        assert "RAM" in message or "95%" in message


@pytest.mark.asyncio
async def test_activity_log_created(proactive_session):
    """Proactive tasks create ActivityLog entries."""
    with patch("ai_office.core.proactive_tasks.async_session") as mock_session_ctx, \
         patch("ai_office.core.proactive_tasks.send_to_chat") as mock_send:
        mock_send.return_value = None

        class FakeCtx:
            async def __aenter__(self):
                return proactive_session
            async def __aexit__(self, *args):
                pass

        mock_session_ctx.return_value = FakeCtx()

        from ai_office.core.proactive_tasks import alice_daily_standup
        await alice_daily_standup()

    # Check activity log was created
    result = await proactive_session.execute(
        select(ActivityLog).where(ActivityLog.action_type == "proactive_standup")
    )
    log = result.scalar_one_or_none()
    assert log is not None
    assert "Стендап" in log.action_description
