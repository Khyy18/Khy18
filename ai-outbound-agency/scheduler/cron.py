"""Cron Scheduler - manages background async loops for sequence and warmup ticks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from scheduler.sequence_runner import SequenceRunner
from scheduler.warmup_scheduler import WarmupScheduler

if TYPE_CHECKING:
    from agents.optimizer import OptimizerAgent
    from scheduler.notifications_scheduler import NotificationsScheduler

logger = logging.getLogger(__name__)

# Default intervals in seconds
_SEQUENCE_INTERVAL = 300   # 5 minutes
_WARMUP_INTERVAL = 900     # 15 minutes
_OPTIMIZER_INTERVAL = 3600  # 1 hour
_NOTIFICATIONS_INTERVAL = 3600  # 1 hour
_USAGE_RESET_INTERVAL = 86400  # 24 hours (checks daily if 1st of month)


class Scheduler:
    """Manages background asyncio tasks for periodic execution of sequence and warmup ticks."""

    def __init__(
        self,
        sequence_runner: SequenceRunner,
        warmup_scheduler: WarmupScheduler,
        optimizer: OptimizerAgent | None = None,
        notifications_scheduler: NotificationsScheduler | None = None,
        redis_url: str = "",
    ) -> None:
        self._sequence_runner = sequence_runner
        self._warmup_scheduler = warmup_scheduler
        self._optimizer = optimizer
        self._notifications_scheduler = notifications_scheduler
        self._redis_url = redis_url
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

        if self._optimizer is not None:
            optimizer_task = asyncio.create_task(
                self._run_loop(
                    self._optimizer_tick,
                    _OPTIMIZER_INTERVAL,
                    "optimizer",
                ),
                name="scheduler:optimizer",
            )
            self._tasks.append(optimizer_task)

        if self._notifications_scheduler is not None:
            notifications_task = asyncio.create_task(
                self._run_loop(
                    self._notifications_scheduler.weekly_digest_tick,
                    _NOTIFICATIONS_INTERVAL,
                    "notifications",
                ),
                name="scheduler:notifications",
            )
            self._tasks.append(notifications_task)

        # Monthly usage reset task (checks daily, resets on 1st of month)
        if self._redis_url:
            usage_reset_task = asyncio.create_task(
                self._run_loop(
                    self._monthly_usage_reset_tick,
                    _USAGE_RESET_INTERVAL,
                    "usage_reset",
                ),
                name="scheduler:usage_reset",
            )
            self._tasks.append(usage_reset_task)

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

    async def _optimizer_tick(self) -> None:
        """Run one optimizer check cycle."""
        if self._optimizer is None:
            return
        await self._optimizer.auto_check_and_promote()

    async def _monthly_usage_reset_tick(self) -> None:
        """Check if today is the 1st of the month; if so, reset all tenant usage."""
        now = datetime.now(timezone.utc)
        if now.day != 1:
            logger.debug("Not the 1st of the month (day=%d), skipping usage reset", now.day)
            return

        logger.info("Monthly usage reset: resetting all tenant usage counters")
        await monthly_usage_reset(self._redis_url)

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


async def monthly_usage_reset(redis_url: str) -> None:
    """Reset usage counters for the previous month. Called on the 1st of each month.

    Only deletes keys for the previous billing period, not the current month.
    """
    from compliance.usage_limiter import UsageLimiter

    # Calculate previous month's period string
    now = datetime.now(timezone.utc)
    # Go back to the last day of the previous month
    first_of_current = now.replace(day=1)
    last_of_previous = first_of_current - timedelta(days=1)
    previous_period = last_of_previous.strftime("%Y-%m")

    limiter = UsageLimiter(redis_url=redis_url)
    try:
        # Scan for only the previous month's usage keys
        pattern = f"usage:*:{previous_period}:*"
        cursor = 0
        deleted_count = 0
        while True:
            cursor, keys = await limiter._redis.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                await limiter._redis.delete(*keys)
                deleted_count += len(keys)
            if cursor == 0:
                break
        logger.info(
            "Monthly usage reset complete: deleted %d usage keys for period %s",
            deleted_count,
            previous_period,
        )
    finally:
        await limiter.close()
