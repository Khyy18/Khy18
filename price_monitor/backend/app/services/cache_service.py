"""Redis cache wrapper with TTL and invalidation."""
from __future__ import annotations


import logging

from app.db.redis_client import cache_delete, cache_get, cache_set

logger = logging.getLogger(__name__)

class CacheService:
    """High-level cache service wrapping Redis operations."""

    DEFAULT_TTL = 300  # 5 minutes

    async def get(self, key: str):
        """Get value from cache."""
        return await cache_get(key)

    async def set(self, key: str, value, ttl: int | None = None):
        """Set value in cache with TTL."""
        await cache_set(key, value, ttl=ttl or self.DEFAULT_TTL)

    async def delete(self, key: str):
        """Delete a key from cache."""
        await cache_delete(key)

    async def invalidate_pattern(self, prefix: str):
        """Invalidate all keys matching a prefix pattern."""
        from app.db.redis_client import get_redis

        try:
            r = await get_redis()
            cursor = 0
            while True:
                cursor, keys = await r.scan(cursor, match=f"{prefix}*", count=100)
                if keys:
                    await r.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning("Cache invalidation failed for prefix=%s: %s", prefix, e)

cache_service = CacheService()
