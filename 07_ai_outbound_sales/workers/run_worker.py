"""ARQ worker entry point. Run with: python -m workers.run_worker"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from workers.config import redis_settings
from workers.email_worker import send_email_task, send_warmup_task
from workers.linkedin_worker import (
    linkedin_connect_task,
    linkedin_message_task,
    linkedin_view_task,
)
from workers.conversation_worker import handle_reply_task
from workers.optimizer_worker import check_significance_task, generate_variants_task

logger = logging.getLogger(__name__)


async def on_startup(ctx: dict[str, Any]) -> None:
    """Initialize shared resources stored in ctx for reuse across task invocations."""
    from core.config import settings
    from core.llm import FallbackLLMClient
    from channels.email.sender import AsyncEmailSender

    # Shared Redis connection
    ctx["redis"] = aioredis.from_url(settings.redis_url, decode_responses=True)

    # Shared email sender
    smtp_accounts = json.loads(settings.smtp_domains) if settings.smtp_domains else []
    if smtp_accounts:
        ctx["email_sender"] = AsyncEmailSender(
            smtp_accounts=smtp_accounts,
            redis_url=settings.redis_url,
        )
    else:
        ctx["email_sender"] = None

    # Shared LLM fallback client
    provider_configs = {
        "openai": {
            "provider": "openai",
            "api_key": settings.openai_api_key,
            "model": settings.llm_openai_model,
            "timeout": settings.llm_openai_timeout,
        },
        "anthropic": {
            "provider": "anthropic",
            "api_key": settings.anthropic_api_key,
            "model": settings.llm_anthropic_model,
            "timeout": settings.llm_anthropic_timeout,
        },
        "groq": {
            "provider": "groq",
            "api_key": settings.groq_api_key,
            "model": settings.llm_groq_model,
            "timeout": settings.llm_groq_timeout,
        },
    }
    chain_names = [
        p.strip()
        for p in settings.llm_fallback_chain.split(",")
        if p.strip()
    ]
    fallback_providers = [
        provider_configs[name]
        for name in chain_names
        if name in provider_configs
    ]
    ctx["llm_client"] = FallbackLLMClient(
        providers=fallback_providers,
        redis_url=settings.redis_url,
    )

    logger.info("Worker startup: shared resources initialized")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    """Clean up shared resources on worker shutdown."""
    redis_conn = ctx.get("redis")
    if redis_conn:
        await redis_conn.close()

    email_sender = ctx.get("email_sender")
    if email_sender:
        await email_sender.close()

    llm_client = ctx.get("llm_client")
    if llm_client:
        await llm_client.close()

    logger.info("Worker shutdown: shared resources cleaned up")


class WorkerSettings:
    """ARQ WorkerSettings class defining all background tasks."""

    redis_settings = redis_settings
    job_timeout = 300
    max_tries = 3
    health_check_interval = 30

    on_startup = on_startup
    on_shutdown = on_shutdown

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
