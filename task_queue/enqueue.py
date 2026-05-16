"""Хелперы для постановки задач в очередь ARQ."""

from __future__ import annotations

from typing import Any

from arq import ArqRedis, create_pool

from task_queue.config import QUEUE_NAME, get_redis_settings


async def _get_pool() -> ArqRedis:
    """Создать пул подключений к Redis для ARQ."""
    return await create_pool(get_redis_settings())


async def enqueue_freelance_scan() -> Any:
    """Поставить задачу сканирования фриланс-площадок."""
    pool = await _get_pool()
    try:
        job = await pool.enqueue_job(
            "freelance_scan_task",
            _queue_name=QUEUE_NAME,
        )
        return job
    finally:
        await pool.aclose()


async def enqueue_offer_generation(
    user_tg_id: int,
    user_name: str,
    amount: float,
    service_description: str,
) -> Any:
    """Поставить задачу генерации PDF-оферты."""
    pool = await _get_pool()
    try:
        job = await pool.enqueue_job(
            "generate_offer_task",
            user_tg_id,
            user_name,
            amount,
            service_description,
            _queue_name=QUEUE_NAME,
        )
        return job
    finally:
        await pool.aclose()


async def enqueue_viral_notification(
    referrer_tg_id: int,
    bonus_info: str,
) -> Any:
    """Поставить задачу отправки реферального уведомления."""
    pool = await _get_pool()
    try:
        job = await pool.enqueue_job(
            "viral_notification_task",
            referrer_tg_id,
            bonus_info,
            _queue_name=QUEUE_NAME,
        )
        return job
    finally:
        await pool.aclose()
