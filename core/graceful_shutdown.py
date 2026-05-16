"""Graceful shutdown manager for coordinating application shutdown.

Handles SIGTERM/SIGINT signals, tracks in-flight tasks, and ensures
all operations complete before the process exits.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

logger = logging.getLogger(__name__)

# Maximum time to wait for in-flight tasks during shutdown
SHUTDOWN_TIMEOUT_SECONDS = 30


class GracefulShutdownManager:
    """Manages graceful shutdown of the application.

    Installs signal handlers for SIGTERM and SIGINT, tracks in-flight
    tasks, and provides a coordinated shutdown sequence that waits
    for active work to complete before closing resources.
    """

    def __init__(self) -> None:
        """Initialize the shutdown manager."""
        self._shutting_down: bool = False
        self._in_flight_tasks: set[str] = set()
        self._shutdown_event: asyncio.Event = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_shutting_down(self) -> bool:
        """Whether the application is currently shutting down."""
        return self._shutting_down

    @property
    def in_flight_count(self) -> int:
        """Number of currently tracked in-flight tasks."""
        return len(self._in_flight_tasks)

    def register(self) -> None:
        """Install signal handlers for SIGTERM and SIGINT.

        Must be called from the main thread during application startup.
        """
        self._loop = asyncio.get_event_loop()

        try:
            self._loop.add_signal_handler(
                signal.SIGTERM, self._handle_signal, signal.SIGTERM
            )
            self._loop.add_signal_handler(
                signal.SIGINT, self._handle_signal, signal.SIGINT
            )
            logger.info("Graceful shutdown handlers registered (SIGTERM, SIGINT)")
        except (NotImplementedError, OSError):
            # Signal handlers may not be supported on all platforms (e.g., Windows)
            logger.warning(
                "Could not register signal handlers; "
                "graceful shutdown via signals not available on this platform"
            )

    def _handle_signal(self, sig: signal.Signals) -> None:
        """Handle incoming shutdown signal.

        Args:
            sig: The signal received.
        """
        logger.info(
            "Received signal %s, initiating graceful shutdown", sig.name
        )
        self._shutting_down = True
        self._shutdown_event.set()

    def track_task(self, task_id: str) -> None:
        """Register an in-flight task.

        Args:
            task_id: Unique identifier for the task.
        """
        if self._shutting_down:
            logger.warning(
                "Cannot track task %s - shutdown in progress", task_id
            )
            return
        self._in_flight_tasks.add(task_id)
        logger.debug("Task tracked: %s (total: %d)", task_id, len(self._in_flight_tasks))

    def complete_task(self, task_id: str) -> None:
        """Mark a task as completed and remove from tracking.

        Args:
            task_id: Unique identifier for the task to complete.
        """
        self._in_flight_tasks.discard(task_id)
        logger.debug(
            "Task completed: %s (remaining: %d)",
            task_id,
            len(self._in_flight_tasks),
        )

    async def shutdown(self) -> None:
        """Execute the graceful shutdown sequence.

        Stops accepting new tasks, waits for in-flight tasks to complete
        (up to SHUTDOWN_TIMEOUT_SECONDS), then signals completion.
        """
        self._shutting_down = True
        logger.info(
            "Starting graceful shutdown. In-flight tasks: %d",
            len(self._in_flight_tasks),
        )

        # Wait for in-flight tasks to complete (with timeout)
        elapsed = 0.0
        poll_interval = 0.5
        while self._in_flight_tasks and elapsed < SHUTDOWN_TIMEOUT_SECONDS:
            remaining = len(self._in_flight_tasks)
            logger.info(
                "Waiting for %d in-flight task(s) to complete (%.1fs elapsed)",
                remaining,
                elapsed,
            )
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        if self._in_flight_tasks:
            logger.warning(
                "Shutdown timeout reached. %d task(s) still in-flight: %s",
                len(self._in_flight_tasks),
                list(self._in_flight_tasks)[:10],
            )
        else:
            logger.info("All in-flight tasks completed successfully")

        logger.info("Graceful shutdown complete")
