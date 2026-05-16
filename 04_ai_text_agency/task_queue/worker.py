"""ARQ worker entry point.

Запуск: arq task_queue.worker.WorkerSettings
"""

from logging_config import get_logger
from task_queue.config import JOB_TIMEOUT, MAX_JOBS, QUEUE_NAME, get_redis_settings
from task_queue.tasks import (
    backup_task,
    content_generation_task,
    freelance_scan_task,
    generate_offer_task,
    retry_webhook_task,
    viral_notification_task,
)

log = get_logger(__name__)


async def on_worker_shutdown(ctx: dict) -> None:
    """Graceful shutdown: drain running jobs before worker exits."""
    log.info("worker_shutdown_initiated")
    # ARQ handles cancellation of running jobs internally;
    # this hook allows custom cleanup (flush buffers, close sessions, etc.)
    session = ctx.get("session")
    if session and not session.closed:
        await session.close()
    log.info("worker_shutdown_complete")


class WorkerSettings:
    """Настройки ARQ worker."""

    redis_settings = get_redis_settings()
    functions = [
        backup_task,
        content_generation_task,
        freelance_scan_task,
        generate_offer_task,
        retry_webhook_task,
        viral_notification_task,
    ]
    job_timeout = JOB_TIMEOUT
    max_jobs = MAX_JOBS
    queue_name = QUEUE_NAME
    on_worker_shutdown = on_worker_shutdown
