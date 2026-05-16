"""Tests for the graceful shutdown manager."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from core.graceful_shutdown import GracefulShutdownManager, SHUTDOWN_TIMEOUT_SECONDS


class TestGracefulShutdownManager:
    """Tests for GracefulShutdownManager."""

    @pytest.mark.asyncio
    async def test_track_and_complete_task(self):
        """Tracking a task increases in_flight_count, completing it decreases."""
        manager = GracefulShutdownManager()

        assert manager.in_flight_count == 0

        manager.track_task("task-1")
        assert manager.in_flight_count == 1

        manager.track_task("task-2")
        assert manager.in_flight_count == 2

        manager.complete_task("task-1")
        assert manager.in_flight_count == 1

        manager.complete_task("task-2")
        assert manager.in_flight_count == 0

    @pytest.mark.asyncio
    async def test_shutdown_waits_for_inflight_tasks(self):
        """Shutdown waits for in-flight tasks to complete within the timeout window."""
        manager = GracefulShutdownManager()
        manager.track_task("task-1")

        async def complete_after_delay():
            await asyncio.sleep(0.2)
            manager.complete_task("task-1")

        # Start the task completion in the background
        asyncio.create_task(complete_after_delay())

        # Shutdown should wait and complete normally
        with patch("core.graceful_shutdown.SHUTDOWN_TIMEOUT_SECONDS", 5):
            await manager.shutdown()

        assert manager.in_flight_count == 0
        assert manager.is_shutting_down is True

    @pytest.mark.asyncio
    async def test_shutdown_timeout_with_stuck_tasks(self):
        """Shutdown exits after timeout even if tasks are not completed."""
        manager = GracefulShutdownManager()
        manager.track_task("stuck-task")

        # Patch timeout to a very short value
        with patch("core.graceful_shutdown.SHUTDOWN_TIMEOUT_SECONDS", 0.5):
            await manager.shutdown()

        # Task is still in-flight but shutdown completed due to timeout
        assert manager.in_flight_count == 1
        assert manager.is_shutting_down is True

    @pytest.mark.asyncio
    async def test_shutting_down_prevents_new_tasks(self):
        """Setting _shutting_down=True prevents new tasks from being tracked."""
        manager = GracefulShutdownManager()

        # Track a task normally
        manager.track_task("task-before")
        assert manager.in_flight_count == 1

        # Set shutting down
        manager._shutting_down = True

        # Attempt to track new task should be rejected
        manager.track_task("task-after")
        assert "task-after" not in manager._in_flight_tasks
        assert manager.in_flight_count == 1  # Still only the first task
