"""AsyncIO-based scheduler for proactive agent tasks."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Awaitable, Optional

from ai_office.core.config import settings

logger = logging.getLogger(__name__)


class ScheduledTask:
    """A registered scheduled task with its timing configuration."""

    def __init__(
        self,
        name: str,
        coro_factory: Callable[[], Awaitable[None]],
        hour: Optional[int] = None,
        minute: int = 0,
        day_of_week: Optional[str] = None,
        interval_hours: Optional[float] = None,
    ):
        self.name = name
        self.coro_factory = coro_factory
        self.hour = hour
        self.minute = minute
        self.day_of_week = day_of_week
        self.interval_hours = interval_hours

    def seconds_until_next_run(self) -> float:
        """Calculate seconds until the next scheduled execution."""
        now = datetime.now(timezone.utc)

        if self.interval_hours is not None:
            return self.interval_hours * 3600

        if self.day_of_week is not None:
            # Weekly: specific day + hour
            days = [
                "monday", "tuesday", "wednesday", "thursday",
                "friday", "saturday", "sunday",
            ]
            target_day = days.index(self.day_of_week.lower())
            current_day = now.weekday()
            days_ahead = target_day - current_day
            if days_ahead < 0:
                days_ahead += 7

            target = now.replace(
                hour=self.hour or 0, minute=self.minute, second=0, microsecond=0
            )
            import datetime as dt
            target = target + dt.timedelta(days=days_ahead)
            if target <= now:
                target = target + dt.timedelta(days=7)
            return (target - now).total_seconds()

        if self.hour is not None:
            # Daily: specific hour
            target = now.replace(
                hour=self.hour, minute=self.minute, second=0, microsecond=0
            )
            if target <= now:
                import datetime as dt
                target = target + dt.timedelta(days=1)
            return (target - now).total_seconds()

        # Fallback: run every hour
        return 3600


class Scheduler:
    """AsyncIO-based scheduler for periodic proactive tasks.

    Uses asyncio.create_task + asyncio.sleep loops for scheduling.
    Integrates with shutdown_event for graceful stop.
    """

    def __init__(self):
        self._tasks: list[ScheduledTask] = []
        self._running_tasks: list[asyncio.Task] = []
        self._shutdown_event: Optional[asyncio.Event] = None
        self._started = False

    def register_task(
        self,
        name: str,
        coro_factory: Callable[[], Awaitable[None]],
        hour: Optional[int] = None,
        minute: int = 0,
        day_of_week: Optional[str] = None,
        interval_hours: Optional[float] = None,
    ) -> None:
        """Register a periodic task.

        Args:
            name: Task identifier
            coro_factory: Async callable that produces the coroutine to run
            hour: Hour of day to run (UTC, for daily/weekly tasks)
            minute: Minute of hour to run
            day_of_week: Day name for weekly tasks (e.g., 'monday')
            interval_hours: Run every N hours (for recurring tasks)
        """
        task = ScheduledTask(
            name=name,
            coro_factory=coro_factory,
            hour=hour,
            minute=minute,
            day_of_week=day_of_week,
            interval_hours=interval_hours,
        )
        self._tasks.append(task)

    async def start(self, shutdown_event: Optional[asyncio.Event] = None) -> None:
        """Start the scheduler.

        No-op if settings.enable_proactive is False.
        """
        if not settings.enable_proactive:
            logger.info("Proactive scheduler disabled (enable_proactive=False)")
            return

        self._shutdown_event = shutdown_event
        self._started = True

        for scheduled_task in self._tasks:
            asyncio_task = asyncio.create_task(
                self._run_loop(scheduled_task)
            )
            self._running_tasks.append(asyncio_task)

        logger.info(
            "Scheduler started with %d tasks: %s",
            len(self._tasks),
            [t.name for t in self._tasks],
        )

    async def stop(self) -> None:
        """Stop all running scheduled tasks."""
        for task in self._running_tasks:
            task.cancel()
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks, return_exceptions=True)
        self._running_tasks.clear()
        self._started = False
        logger.info("Scheduler stopped")

    async def _run_loop(self, scheduled_task: ScheduledTask) -> None:
        """Internal loop: sleep until next run, execute, repeat."""
        try:
            while True:
                # Check shutdown
                if self._shutdown_event and self._shutdown_event.is_set():
                    break

                delay = scheduled_task.seconds_until_next_run()
                logger.debug(
                    "Task '%s' next run in %.0f seconds",
                    scheduled_task.name,
                    delay,
                )

                # Sleep with shutdown check
                try:
                    if self._shutdown_event:
                        done, pending = await asyncio.wait(
                            [
                                asyncio.create_task(asyncio.sleep(delay)),
                                asyncio.create_task(self._shutdown_event.wait()),
                            ],
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        # Cancel the pending task to avoid leaks
                        for t in pending:
                            t.cancel()
                        if self._shutdown_event.is_set():
                            break
                    else:
                        await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    break

                # Execute the task
                try:
                    logger.info("Executing proactive task: %s", scheduled_task.name)
                    await scheduled_task.coro_factory()
                except Exception as e:
                    logger.error(
                        "Proactive task '%s' failed: %s",
                        scheduled_task.name,
                        str(e),
                    )
        except asyncio.CancelledError:
            pass

    @property
    def registered_tasks(self) -> list[ScheduledTask]:
        """Get list of registered tasks."""
        return self._tasks.copy()

    @property
    def is_started(self) -> bool:
        """Check if scheduler is running."""
        return self._started


# Module-level instance
scheduler = Scheduler()
