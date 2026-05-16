"""ARQ worker entry point.

Запуск: arq task_queue.worker.WorkerSettings
"""

from task_queue.config import JOB_TIMEOUT, MAX_JOBS, QUEUE_NAME, get_redis_settings
from task_queue.tasks import (
    freelance_scan_task,
    generate_offer_task,
    viral_notification_task,
)


class WorkerSettings:
    """Настройки ARQ worker."""

    redis_settings = get_redis_settings()
    functions = [
        freelance_scan_task,
        generate_offer_task,
        viral_notification_task,
    ]
    job_timeout = JOB_TIMEOUT
    max_jobs = MAX_JOBS
    queue_name = QUEUE_NAME
