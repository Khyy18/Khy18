"""Хелперы для постановки задач в очередь ARQ.

Используют lazy singleton pool: пул Redis-соединений создаётся один раз
при первом вызове get_pool() и переиспользуется для всех последующих
enqueue-операций. Для корректного завершения вызывайте close_pool().
"""

from __future__ import annotations

from typing import Any, Optional

from arq import ArqRedis, create_pool

from task_queue.config import QUEUE_NAME, get_redis_settings

# Lazy singleton pool
_pool: Optional[ArqRedis] = None


async def get_pool() -> ArqRedis:
    """Получить или создать singleton пул подключений к Redis для ARQ."""
    global _pool
    if _pool is None:
        _pool = await create_pool(get_redis_settings())
    return _pool


async def close_pool() -> None:
    """Закрыть singleton пул (для graceful shutdown)."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def enqueue_freelance_scan() -> Any:
    """Поставить задачу сканирования фриланс-площадок."""
    pool = await get_pool()
    job = await pool.enqueue_job(
        "freelance_scan_task",
        _queue_name=QUEUE_NAME,
    )
    return job


async def enqueue_offer_generation(
    user_tg_id: int,
    user_name: str,
    amount: float,
    service_description: str,
) -> Any:
    """Поставить задачу генерации PDF-оферты."""
    pool = await get_pool()
    job = await pool.enqueue_job(
        "generate_offer_task",
        user_tg_id,
        user_name,
        amount,
        service_description,
        _queue_name=QUEUE_NAME,
    )
    return job


async def enqueue_viral_notification(
    referrer_tg_id: int,
    bonus_info: str,
) -> Any:
    """Поставить задачу отправки реферального уведомления."""
    pool = await get_pool()
    job = await pool.enqueue_job(
        "viral_notification_task",
        referrer_tg_id,
        bonus_info,
        _queue_name=QUEUE_NAME,
    )
    return job
