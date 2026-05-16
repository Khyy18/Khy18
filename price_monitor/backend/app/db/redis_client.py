"""Redis connection pool and helper functions."""
from __future__ import annotations


import json
import logging
from typing import Any, Optional

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[redis.Redis] = None

async def get_redis() -> redis.Redis:
    """Get or create Redis connection pool."""
    global _pool
    if _pool is None:
        _pool = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _pool

async def cache_get(key: str) -> Any | None:
    """Get cached value by key. Returns None on miss or error."""
    try:
        r = await get_redis()
        value = await r.get(key)
        if value is not None:
            return json.loads(value)
    except Exception as e:
        logger.warning("Redis GET error for key=%s: %s", key, e)
    return None

async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    """Set cached value with TTL in seconds."""
    try:
        r = await get_redis()
        await r.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as e:
        logger.warning("Redis SET error for key=%s: %s", key, e)

async def cache_delete(key: str) -> None:
    """Delete cached value by key."""
    try:
        r = await get_redis()
        await r.delete(key)
    except Exception as e:
        logger.warning("Redis DELETE error for key=%s: %s", key, e)

async def close_redis() -> None:
    """Close Redis connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
