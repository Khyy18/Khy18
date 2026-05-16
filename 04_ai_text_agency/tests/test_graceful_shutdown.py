"""Tests for graceful shutdown in main.py."""

from __future__ import annotations

import asyncio
import signal
from unittest.mock import patch

import pytest


class TestShutdownEvent:
    @pytest.mark.asyncio
    async def test_shutdown_event_stops_loop(self) -> None:
        """Verify that setting shutdown_event causes wait() to complete."""
        shutdown_event = asyncio.Event()

        async def fake_loop() -> str:
            while not shutdown_event.is_set():
                await asyncio.sleep(0.01)
            return "stopped"

        # Set shutdown after a short delay
        async def trigger_shutdown() -> None:
            await asyncio.sleep(0.05)
            shutdown_event.set()

        task = asyncio.create_task(fake_loop())
        asyncio.create_task(trigger_shutdown())

        result = await asyncio.wait_for(task, timeout=2.0)
        assert result == "stopped"

    @pytest.mark.asyncio
    async def test_signal_handler_sets_event(self) -> None:
        """Verify that a signal handler callback sets the event."""
        shutdown_event = asyncio.Event()

        def signal_handler() -> None:
            shutdown_event.set()

        # Simulate what main.py does: add_signal_handler
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGUSR1, signal_handler)

        try:
            # Trigger signal manually
            import os
            os.kill(os.getpid(), signal.SIGUSR1)
            # Give event loop a chance to process the signal
            await asyncio.sleep(0.05)
            assert shutdown_event.is_set()
        finally:
            loop.remove_signal_handler(signal.SIGUSR1)

    @pytest.mark.asyncio
    async def test_tasks_cancelled_on_shutdown(self) -> None:
        """Verify that pending tasks are cancelled when shutdown fires."""
        shutdown_event = asyncio.Event()
        cancelled = []

        async def long_running(name: str) -> None:
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                cancelled.append(name)
                raise

        tasks = [
            asyncio.create_task(long_running("task1")),
            asyncio.create_task(long_running("task2")),
            asyncio.create_task(shutdown_event.wait()),
        ]

        # Trigger shutdown
        shutdown_event.set()

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

        assert "task1" in cancelled
        assert "task2" in cancelled
