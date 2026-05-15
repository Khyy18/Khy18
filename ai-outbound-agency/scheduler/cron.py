"""Cron Scheduler - manages background async loops for sequence and warmup ticks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from scheduler.sequence_runner import SequenceRunner
from scheduler.warmup_scheduler import WarmupScheduler

logger = logging.getLogger(__name__)

# Default intervals in seconds
_SEQUENCE_INTERVAL = 300   # 5 minutes
_WARMUP_INTERVAL = 900     # 15 minutes


class Scheduler:
    """Manages background asyncio tasks for periodic execution of sequence and warmup ticks."""

    def __init__(
        self,
        sequence_runner: SequenceRunner,
        warmup_scheduler: WarmupScheduler,
    ) -> None:
        self._sequence_runner = sequence_runner
        self._warmup_scheduler = warmup_scheduler
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        """Start background scheduler loops."""
        logger.info("Starting scheduler background tasks")
        sequence_task = asyncio.create_task(
            self._run_loop(
                self._sequence_runner.run_tick,
                _SEQUENCE_INTERVAL,
                "sequence_runner",
            ),
            name="scheduler:sequence_runner",
        )
        warmup_task = asyncio.create_task(
            self._run_loop(
                self._warmup_scheduler.run_warmup_tick,
                _WARMUP_INTERVAL,
                "warmup_scheduler",
            ),
            name="scheduler:warmup_scheduler",
        )
        self._tasks = [sequence_task, warmup_task]
        logger.info("Scheduler started with %d background tasks", len(self._tasks))

    async def stop(self) -> None:
        """Stop all background scheduler tasks gracefully."""
        logger.info("Stopping scheduler background tasks")
        for task in self._tasks:
            task.cancel()

        # Await cancellation with a timeout
        if self._tasks:
            results = await asyncio.gather(
                *self._tasks, return_exceptions=True
            )
            for i, result in enumerate(results):
                if isinstance(result, asyncio.CancelledError):
                    logger.debug("Task %d cancelled successfully", i)
                elif isinstance(result, Exception):
                    logger.error(
                        "Task %d raised an error during shutdown: %s",
                        i,
                        result,
                    )

        self._tasks = []
        logger.info("Scheduler stopped")

    async def _run_loop(
        self,
        coro_factory: Callable[[], Awaitable[None]],
        interval: int,
        name: str,
    ) -> None:
        """Generic loop runner that executes a coroutine at fixed intervals.

        Catches and logs exceptions from individual ticks without stopping the loop.
        """
        logger.info("Loop '%s' started (interval=%ds)", name, interval)
        while True:
            try:
                await coro_factory()
            except asyncio.CancelledError:
                logger.info("Loop '%s' cancelled", name)
                raise
            except Exception as exc:
                logger.error(
                    "Error in loop '%s': %s", name, exc, exc_info=True
                )

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.info("Loop '%s' cancelled during sleep", name)
                raise
