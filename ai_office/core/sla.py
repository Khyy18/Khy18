"""SLA Engine для мониторинга соблюдения сроков задач."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.models import Task

logger = logging.getLogger(__name__)


class SLAEngine:
    """Движок мониторинга SLA (Service Level Agreements)."""

    SLA_TARGETS = {
        "urgent": 30,
        "high": 120,
        "medium": 300,
        "low": 900,
    }

    async def compute_sla_target(self, priority: str) -> int:
        """Return SLA target in seconds for given priority."""
        return self.SLA_TARGETS.get(priority, 300)

    async def check_breaches(self, session: AsyncSession) -> list:
        """Query in-progress tasks where elapsed time > sla_target_seconds."""
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(Task).where(
                Task.status == "in_progress",
                Task.sla_target_seconds.isnot(None),
            )
        )
        tasks = result.scalars().all()

        breaches = []
        for task in tasks:
            # Calculate elapsed seconds since creation
            created = task.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            elapsed = (now - created).total_seconds()

            if elapsed > task.sla_target_seconds:
                breaches.append({
                    "task_id": task.id,
                    "description": task.description,
                    "priority": task.priority,
                    "sla_target_seconds": task.sla_target_seconds,
                    "elapsed_seconds": int(elapsed),
                    "breach_seconds": int(elapsed - task.sla_target_seconds),
                })

        return breaches

    async def get_sla_status(self, session: AsyncSession) -> dict:
        """Return SLA compliance statistics.

        Returns:
            dict with compliance_percent, avg_response_by_priority, breaches_count
        """
        # Get all tasks with SLA targets
        result = await session.execute(
            select(Task).where(Task.sla_target_seconds.isnot(None))
        )
        all_tasks = result.scalars().all()

        if not all_tasks:
            return {
                "compliance_percent": 100.0,
                "avg_response_by_priority": {},
                "breaches_count": 0,
            }

        now = datetime.now(timezone.utc)
        breaches_count = 0
        response_times: dict[str, list[float]] = {}

        for task in all_tasks:
            created = task.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)

            # Calculate response time
            if task.response_started_at:
                started = task.response_started_at
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                response_time = (started - created).total_seconds()
            elif task.status in ("done", "closed"):
                # Use closed_at as fallback
                if task.closed_at:
                    closed = task.closed_at
                    if closed.tzinfo is None:
                        closed = closed.replace(tzinfo=timezone.utc)
                    response_time = (closed - created).total_seconds()
                else:
                    response_time = 0.0
            else:
                response_time = (now - created).total_seconds()

            # Track response times by priority
            priority = task.priority or "medium"
            if priority not in response_times:
                response_times[priority] = []
            response_times[priority].append(response_time)

            # Check breach
            if task.status == "in_progress":
                elapsed = (now - created).total_seconds()
                if elapsed > task.sla_target_seconds:
                    breaches_count += 1

        # Calculate averages
        avg_response_by_priority = {}
        for priority, times in response_times.items():
            if times:
                avg_response_by_priority[priority] = sum(times) / len(times)

        # Compliance: tasks that are NOT breaching / total active tasks with SLA
        active_tasks = [t for t in all_tasks if t.status == "in_progress"]
        if active_tasks:
            compliance_percent = (
                (len(active_tasks) - breaches_count) / len(active_tasks) * 100.0
            )
        else:
            compliance_percent = 100.0

        return {
            "compliance_percent": round(compliance_percent, 1),
            "avg_response_by_priority": avg_response_by_priority,
            "breaches_count": breaches_count,
        }


# Module-level instance
sla_engine = SLAEngine()
