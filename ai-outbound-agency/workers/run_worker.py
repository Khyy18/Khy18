"""ARQ worker entry point. Run with: python -m workers.run_worker"""

from __future__ import annotations

from workers.config import redis_settings
from workers.email_worker import send_email_task, send_warmup_task
from workers.linkedin_worker import (
    linkedin_connect_task,
    linkedin_message_task,
    linkedin_view_task,
)
from workers.conversation_worker import handle_reply_task
from workers.optimizer_worker import check_significance_task, generate_variants_task


class WorkerSettings:
    """ARQ WorkerSettings class defining all background tasks."""

    redis_settings = redis_settings
    job_timeout = 300
    max_tries = 3
    health_check_interval = 30

    functions = [
        send_email_task,
        send_warmup_task,
        linkedin_connect_task,
        linkedin_message_task,
        linkedin_view_task,
        handle_reply_task,
        check_significance_task,
        generate_variants_task,
    ]


if __name__ == "__main__":
    import arq.worker

    arq.worker.run_worker(WorkerSettings)  # type: ignore[arg-type]
