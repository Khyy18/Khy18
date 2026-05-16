"""Redis cache with graceful fallback."""

import functools
import json
from typing import Optional

from ai_office.core.config import settings
from ai_office.core.logging import get_logger

logger = get_logger(__name__)


class AsyncRedisCache:
    """Async Redis cache with graceful fallback to no-op."""

    def __init__(self):
        self._redis = None
        self._available = False

    async def connect(self):
        if not settings.redis_url:
            logger.info("Redis URL not configured, cache disabled")
            return
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(
                settings.redis_url, decode_responses=True
            )
            await self._redis.ping()
            self._available = True
            logger.info("Redis cache connected")
        except Exception as e:
            logger.warning(f"Redis unavailable, cache disabled: {e}")
            self._available = False

    async def disconnect(self):
        if self._redis:
            await self._redis.close()

    async def get(self, key: str) -> Optional[str]:
        if not self._available:
            return None
        try:
            return await self._redis.get(key)
        except Exception:
            return None

    async def set(self, key: str, value: str, ttl: int = 3):
        if not self._available:
            return
        try:
            await self._redis.set(key, value, ex=ttl)
        except Exception:
            pass

    async def delete(self, key: str):
        if not self._available:
            return
        try:
            await self._redis.delete(key)
        except Exception:
            pass

    async def invalidate_pattern(self, pattern: str):
        """Delete keys matching pattern using SCAN (non-blocking) instead of KEYS."""
        if not self._available:
            return
        try:
            batch = []
            async for key in self._redis.scan_iter(match=pattern, count=100):
                batch.append(key)
                if len(batch) >= 100:
                    await self._redis.delete(*batch)
                    batch = []
            if batch:
                await self._redis.delete(*batch)
        except Exception:
            pass


# Singleton
cache = AsyncRedisCache()


def cached(ttl: int = 3, key: str = ""):
    """Decorator to cache FastAPI endpoint responses.

    Args:
        ttl: Cache TTL in seconds.
        key: Explicit cache key string. If not provided, uses the function name.
             This avoids including non-serializable kwargs (like DB sessions) in the key.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = key or func.__name__

            # Try cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return json.loads(cached_value)

            # Call original
            result = await func(*args, **kwargs)

            # Store in cache
            try:
                await cache.set(
                    cache_key, json.dumps(result, default=str), ttl=ttl
                )
            except Exception:
                pass

            return result

        return wrapper

    return decorator
