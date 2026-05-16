"""Модуль фоновых задач на базе ARQ (asyncio Redis queue)."""

from task_queue.enqueue import (
    enqueue_freelance_scan,
    enqueue_offer_generation,
    enqueue_viral_notification,
)
from task_queue.tasks import (
    freelance_scan_task,
    generate_offer_task,
    viral_notification_task,
)
from task_queue.worker import WorkerSettings

__all__ = [
    "freelance_scan_task",
    "generate_offer_task",
    "viral_notification_task",
    "WorkerSettings",
    "enqueue_freelance_scan",
    "enqueue_offer_generation",
    "enqueue_viral_notification",
]
