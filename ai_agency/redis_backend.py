"""Redis backend for queues, cache, and rate limiting with graceful fallback."""

import json
import logging
import time
from typing import Optional

import config

# Graceful import
try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None

logger = logging.getLogger(__name__)


class RedisBackend:
    """Redis backend providing queue, cache, rate limiting, and session operations."""

    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._redis: Optional["aioredis.Redis"] = None

    async def connect(self) -> None:
        """Establish Redis connection."""
        if aioredis is None:
            logger.warning("redis package not installed. Redis backend disabled.")
            return
        try:
            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
            )
            await self._redis.ping()
            logger.info("Redis connected: %s", self._redis_url)
        except Exception as e:
            logger.warning("Failed to connect to Redis: %s", e)
            self._redis = None

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    @property
    def is_connected(self) -> bool:
        """Check if Redis is connected."""
        return self._redis is not None

    # --- Queue operations ---

    async def enqueue(self, queue_name: str, data: dict) -> None:
        """LPUSH serialized JSON to queue."""
        if not self._redis:
            return
        await self._redis.lpush(queue_name, json.dumps(data))

    async def dequeue(self, queue_name: str) -> Optional[dict]:
        """RPOP from queue and deserialize."""
        if not self._redis:
            return None
        raw = await self._redis.rpop(queue_name)
        if raw:
            return json.loads(raw)
        return None

    # --- Cache operations ---

    async def cache_get(self, key: str) -> Optional[str]:
        """GET value from cache."""
        if not self._redis:
            return None
        return await self._redis.get(key)

    async def cache_set(self, key: str, value: str, ttl: int = 3600) -> None:
        """SET value with TTL."""
        if not self._redis:
            return
        await self._redis.set(key, value, ex=ttl)

    # --- Rate limiting ---

    async def rate_limit_check(self, key: str, max_count: int, window_seconds: int) -> bool:
        """
        Sliding window rate limiter using sorted sets.

        Returns True if under the limit (request allowed), False if limit exceeded.
        """
        if not self._redis:
            return True  # Allow if Redis unavailable

        now = time.time()
        window_start = now - window_seconds
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window_seconds)
        results = await pipe.execute()

        current_count = results[2]
        return current_count <= max_count

    # --- Session operations ---

    async def session_get(self, user_id: int) -> Optional[dict]:
        """Get user session data."""
        if not self._redis:
            return None
        raw = await self._redis.get(f"session:{user_id}")
        if raw:
            return json.loads(raw)
        return None

    async def session_set(self, user_id: int, data: dict, ttl: int = 86400) -> None:
        """Set user session data with TTL."""
        if not self._redis:
            return
        await self._redis.set(f"session:{user_id}", json.dumps(data), ex=ttl)

    # --- Health check ---

    async def health_check(self) -> bool:
        """PING Redis to check connectivity."""
        if not self._redis:
            return False
        try:
            return await self._redis.ping()
        except Exception:
            return False


# Module-level singleton
_backend: Optional[RedisBackend] = None


def get_redis() -> Optional[RedisBackend]:
    """Return the Redis backend if configured and connected, else None."""
    return _backend if _backend and _backend.is_connected else None


async def init_redis() -> Optional[RedisBackend]:
    """Initialize the Redis backend singleton if REDIS_URL is set."""
    global _backend
    if not config.REDIS_URL:
        return None
    if aioredis is None:
        logger.warning("redis package not installed. Skipping Redis init.")
        return None
    _backend = RedisBackend(config.REDIS_URL)
    await _backend.connect()
    return _backend


async def close_redis() -> None:
    """Close Redis backend."""
    global _backend
    if _backend:
        await _backend.disconnect()
        _backend = None
