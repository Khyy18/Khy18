"""Тесты модуля task_queue: импорты, корутины, enqueue-хелперы."""

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_task_functions_are_coroutines():
    """Проверяем что задачи - корутины (async функции)."""
    from task_queue.tasks import (
        freelance_scan_task,
        generate_offer_task,
        viral_notification_task,
    )

    assert inspect.iscoroutinefunction(freelance_scan_task)
    assert inspect.iscoroutinefunction(generate_offer_task)
    assert inspect.iscoroutinefunction(viral_notification_task)


def test_worker_settings_has_functions():
    """WorkerSettings содержит список задач и базовую конфигурацию."""
    from task_queue.worker import WorkerSettings

    assert hasattr(WorkerSettings, "functions")
    assert hasattr(WorkerSettings, "job_timeout")
    assert hasattr(WorkerSettings, "max_jobs")
    assert hasattr(WorkerSettings, "queue_name")
    assert len(WorkerSettings.functions) == 3


def test_enqueue_helpers_are_coroutines():
    """Хелперы enqueue - async-функции."""
    from task_queue.enqueue import (
        enqueue_freelance_scan,
        enqueue_offer_generation,
        enqueue_viral_notification,
    )

    assert inspect.iscoroutinefunction(enqueue_freelance_scan)
    assert inspect.iscoroutinefunction(enqueue_offer_generation)
    assert inspect.iscoroutinefunction(enqueue_viral_notification)


@pytest.mark.asyncio
async def test_enqueue_freelance_scan_calls_pool():
    """enqueue_freelance_scan использует singleton пул и ставит задачу."""
    import task_queue.enqueue as enqueue_mod

    mock_pool = AsyncMock()
    mock_pool.enqueue_job = AsyncMock(return_value="job-123")

    # Сбрасываем singleton
    enqueue_mod._pool = None

    with patch("task_queue.enqueue.create_pool", return_value=mock_pool):
        result = await enqueue_mod.enqueue_freelance_scan()

    mock_pool.enqueue_job.assert_called_once_with(
        "freelance_scan_task",
        _queue_name="zenith:queue",
    )
    assert result == "job-123"

    # Cleanup singleton
    enqueue_mod._pool = None


@pytest.mark.asyncio
async def test_enqueue_offer_generation_passes_args():
    """enqueue_offer_generation передаёт аргументы в enqueue_job."""
    import task_queue.enqueue as enqueue_mod

    mock_pool = AsyncMock()
    mock_pool.enqueue_job = AsyncMock(return_value="job-456")

    # Сбрасываем singleton
    enqueue_mod._pool = None

    with patch("task_queue.enqueue.create_pool", return_value=mock_pool):
        result = await enqueue_mod.enqueue_offer_generation(
            user_tg_id=12345,
            user_name="Test User",
            amount=100.0,
            service_description="Test service",
        )

    mock_pool.enqueue_job.assert_called_once_with(
        "generate_offer_task",
        12345,
        "Test User",
        100.0,
        "Test service",
        _queue_name="zenith:queue",
    )
    assert result == "job-456"

    # Cleanup singleton
    enqueue_mod._pool = None


@pytest.mark.asyncio
async def test_enqueue_viral_notification_passes_args():
    """enqueue_viral_notification передаёт referrer_tg_id и bonus_info."""
    import task_queue.enqueue as enqueue_mod

    mock_pool = AsyncMock()
    mock_pool.enqueue_job = AsyncMock(return_value="job-789")

    # Сбрасываем singleton
    enqueue_mod._pool = None

    with patch("task_queue.enqueue.create_pool", return_value=mock_pool):
        result = await enqueue_mod.enqueue_viral_notification(
            referrer_tg_id=99999,
            bonus_info="free order",
        )

    mock_pool.enqueue_job.assert_called_once_with(
        "viral_notification_task",
        99999,
        "free order",
        _queue_name="zenith:queue",
    )
    assert result == "job-789"

    # Cleanup singleton
    enqueue_mod._pool = None
