from __future__ import annotations
import time

import redis.asyncio as aioredis


class RateLimiter:
    """Redis-based sliding window rate limiter."""

    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def check_rate_limit(
        self, key: str, max_requests: int, window_seconds: int
    ) -> bool:
        """Check if request is within the rate limit.

        Returns True if the request is allowed, False if rate limit exceeded.
        """
        now = time.time()
        window_start = now - window_seconds

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        results = await pipe.execute()

        current_count: int = results[1]
        return current_count < max_requests

    async def record_request(self, key: str, window_seconds: int) -> None:
        """Record a request in the sliding window."""
        now = time.time()
        member = f"{now}"

        pipe = self._redis.pipeline()
        pipe.zadd(key, {member: now})
        pipe.expire(key, window_seconds)
        await pipe.execute()

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()
