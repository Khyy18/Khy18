"""Redis-based sliding window rate limiter for FastAPI."""

import logging
import time
from typing import Optional

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


class RateLimiter:
    """Redis-backed sliding window rate limiter.

    Uses sorted sets in Redis to implement a sliding window counter.
    Key pattern: ratelimit:{endpoint}:{user_id}:{window}
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client

    @property
    def redis(self):
        return self._redis

    @redis.setter
    def redis(self, client):
        self._redis = client

    async def check_rate_limit(
        self,
        endpoint: str,
        user_id: str,
        max_requests: int,
        window_seconds: int,
    ) -> bool:
        """Check if request is within rate limit.

        Args:
            endpoint: Endpoint identifier (e.g., "session_start").
            user_id: User identifier.
            max_requests: Maximum requests allowed in window.
            window_seconds: Window duration in seconds.

        Returns:
            True if request is allowed, False if rate limited.
        """
        if self._redis is None:
            # No Redis available, allow all requests
            return True

        now = time.time()
        window_start = now - window_seconds
        key = f"ratelimit:{endpoint}:{user_id}:{window_seconds}"

        pipe = self._redis.pipeline()
        # Remove expired entries
        pipe.zremrangebyscore(key, 0, window_start)
        # Count entries in current window
        pipe.zcard(key)
        # Add current request
        pipe.zadd(key, {f"{now}": now})
        # Set TTL on the key
        pipe.expire(key, window_seconds)

        results = await pipe.execute()
        current_count = results[1]

        if current_count >= max_requests:
            return False

        return True


# Module-level rate limiter instance
rate_limiter = RateLimiter()


def rate_limit(endpoint_name: str, max_requests: int, window_seconds: int):
    """Create a FastAPI dependency for rate limiting.

    Args:
        endpoint_name: Name of the endpoint for the rate limit key.
        max_requests: Maximum number of requests in the window.
        window_seconds: Window duration in seconds.

    Returns:
        A FastAPI dependency function.
    """

    async def _rate_limit_dependency(request: Request):
        # Extract user_id from request body or query params
        # For simplicity, use client IP as fallback identifier
        user_id = request.client.host if request.client else "unknown"

        # Try to get user_id from request state or headers
        if hasattr(request.state, "user_id"):
            user_id = request.state.user_id

        allowed = await rate_limiter.check_rate_limit(
            endpoint_name, user_id, max_requests, window_seconds
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {max_requests} requests per {window_seconds}s.",
            )

    return _rate_limit_dependency
