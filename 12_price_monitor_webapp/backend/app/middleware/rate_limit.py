"""Redis-based rate limiting middleware."""
from __future__ import annotations


import logging
import time

from fastapi import HTTPException, Request, status

from app.db.redis_client import get_redis

logger = logging.getLogger(__name__)

DEFAULT_WINDOW = 60  # seconds
DEFAULT_MAX_REQUESTS = 30

async def check_rate_limit(
    request: Request,
    window: int = DEFAULT_WINDOW,
    max_requests: int = DEFAULT_MAX_REQUESTS,
) -> None:
    """Check Redis-based rate limit for a request.

    Raises HTTP 429 if limit exceeded.
    """
    client_ip = request.client.host if request.client else "unknown"
    key = f"rl:{client_ip}:{request.url.path}"

    try:
        r = await get_redis()
        current = await r.get(key)

        if current is not None and int(current) >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много запросов. Попробуйте позже.",
            )

        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        await pipe.execute()
    except HTTPException:
        raise
    except Exception as e:
        # If Redis is unavailable, allow the request through
        logger.warning("Rate limit check failed: %s", e)
