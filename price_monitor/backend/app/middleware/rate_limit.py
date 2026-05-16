"""Redis-based rate limiting middleware using sliding window with sorted sets."""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from fastapi import HTTPException, Request, status

from app.db.redis_client import get_redis

logger = logging.getLogger(__name__)

DEFAULT_WINDOW = 60  # seconds
DEFAULT_MAX_REQUESTS = 30

# In-memory fallback when Redis is unavailable
_fallback_store: dict[str, list[float]] = defaultdict(list)


async def check_rate_limit(
    request: Request,
    window: int = DEFAULT_WINDOW,
    max_requests: int = DEFAULT_MAX_REQUESTS,
) -> None:
    """Check rate limit using Redis sorted sets (sliding window).

    Uses ZADD with timestamp scores for true sliding window behavior.
    Falls back to in-memory dict if Redis is unavailable.

    Raises HTTP 429 if limit exceeded.
    """
    client_ip = request.client.host if request.client else "unknown"
    endpoint = request.url.path
    key = f"rate_limit:{client_ip}:{endpoint}"
    now = time.time()
    window_start = now - window

    try:
        r = await get_redis()

        # Remove expired entries outside the window
        await r.zremrangebyscore(key, "-inf", window_start)

        # Count current requests in the window
        current_count = await r.zcard(key)

        if current_count >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много запросов. Попробуйте позже.",
            )

        # Add current request with timestamp as score
        await r.zadd(key, {f"{now}": now})

        # Set TTL on the key to auto-cleanup
        await r.expire(key, window + 1)

    except HTTPException:
        raise
    except Exception as e:
        # Redis unavailable - fallback to in-memory sliding window
        logger.warning("Rate limit Redis unavailable, using in-memory fallback: %s", e)
        _check_rate_limit_memory(key, now, window_start, window, max_requests)


def _check_rate_limit_memory(
    key: str,
    now: float,
    window_start: float,
    window: int,
    max_requests: int,
) -> None:
    """In-memory fallback rate limiter using sliding window."""
    # Remove expired timestamps
    _fallback_store[key] = [
        ts for ts in _fallback_store[key] if ts > window_start
    ]

    if len(_fallback_store[key]) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много запросов. Попробуйте позже.",
        )

    _fallback_store[key].append(now)
