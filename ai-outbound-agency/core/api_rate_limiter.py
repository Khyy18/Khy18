"""API rate limiter middleware using Redis sorted sets for sliding window enforcement.

Provides per-endpoint-group rate limiting with configurable limits for
auth, webhook, and regular API endpoints. Gracefully handles Redis
unavailability by allowing requests through.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import redis.asyncio as aioredis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)

# Endpoint group definitions: (path_prefix, max_requests, window_seconds)
ENDPOINT_GROUPS: list[tuple[str, int, int]] = [
    ("/api/auth/", 5, 60),          # Auth endpoints: 5 requests per minute
    ("/webhooks/", 1000, 60),       # Webhook endpoints: 1000 requests per minute
]

# Default limits for /api/* paths
AUTHENTICATED_LIMIT = 100  # 100 requests per minute
UNAUTHENTICATED_LIMIT = 20  # 20 requests per minute
DEFAULT_WINDOW = 60  # 60 seconds


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Redis-based sliding window rate limiter middleware for FastAPI.

    Uses sorted sets to implement a sliding window algorithm. Supports
    different rate limits per endpoint group. Adds standard rate limit
    headers to all responses.

    If Redis is unavailable, requests are allowed through to avoid
    blocking the entire application.
    """

    def __init__(self, app: Any, redis_url: str) -> None:
        """Initialize the rate limiter middleware.

        Args:
            app: The ASGI application.
            redis_url: Redis connection URL.
        """
        super().__init__(app)
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create the Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True
            )
        return self._redis

    def _get_client_identifier(self, request: Request) -> str:
        """Extract client identifier from request.

        Uses user ID from request state if authenticated, otherwise
        falls back to client IP address.
        """
        # Check if user is authenticated (set by auth middleware)
        user = getattr(request.state, "user", None)
        if user and hasattr(user, "id"):
            return f"user:{user.id}"

        # Fall back to IP address
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
        client = request.client
        if client:
            return f"ip:{client.host}"
        return "ip:unknown"

    def _is_authenticated(self, request: Request) -> bool:
        """Check if the request is from an authenticated user."""
        user = getattr(request.state, "user", None)
        return user is not None and hasattr(user, "id")

    def _get_rate_limit(self, path: str, is_authenticated: bool) -> tuple[int, int]:
        """Determine the rate limit for the given path.

        Args:
            path: The request path.
            is_authenticated: Whether the request is authenticated.

        Returns:
            Tuple of (max_requests, window_seconds).
        """
        for prefix, max_requests, window in ENDPOINT_GROUPS:
            if path.startswith(prefix):
                return max_requests, window

        # Default API limits
        if path.startswith("/api/"):
            if is_authenticated:
                return AUTHENTICATED_LIMIT, DEFAULT_WINDOW
            return UNAUTHENTICATED_LIMIT, DEFAULT_WINDOW

        # Non-API paths (health, metrics, static) - no rate limiting
        return 0, 0

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process the request through rate limiting.

        Args:
            request: The incoming request.
            call_next: The next middleware/handler in the chain.

        Returns:
            Response with rate limit headers or 429 if limit exceeded.
        """
        path = request.url.path
        is_authenticated = self._is_authenticated(request)
        max_requests, window = self._get_rate_limit(path, is_authenticated)

        # Skip rate limiting for paths without limits (health, static, etc.)
        if max_requests == 0:
            return await call_next(request)

        client_id = self._get_client_identifier(request)
        rate_key = f"rate_limit:{path.split('/')[1]}:{client_id}"

        # More specific key for endpoint groups
        for prefix, _, _ in ENDPOINT_GROUPS:
            if path.startswith(prefix):
                group = prefix.strip("/").replace("/", ":")
                rate_key = f"rate_limit:{group}:{client_id}"
                break

        try:
            redis = await self._get_redis()
            now = time.time()
            window_start = now - window

            pipe = redis.pipeline()
            pipe.zremrangebyscore(rate_key, 0, window_start)
            pipe.zcard(rate_key)
            results = await pipe.execute()

            current_count: int = results[1]
            remaining = max(0, max_requests - current_count)
            reset_time = int(now + window)

            if current_count >= max_requests:
                # Rate limit exceeded - client must wait for the window to reset
                retry_after = window
                response = JSONResponse(
                    content={
                        "error": "Rate limit exceeded",
                        "retry_after": retry_after,
                    },
                    status_code=429,
                )
                response.headers["Retry-After"] = str(retry_after)
                response.headers["X-RateLimit-Limit"] = str(max_requests)
                response.headers["X-RateLimit-Remaining"] = "0"
                response.headers["X-RateLimit-Reset"] = str(reset_time)
                return response

            # Record this request
            member = f"{now}:{id(request)}"
            pipe2 = redis.pipeline()
            pipe2.zadd(rate_key, {member: now})
            pipe2.expire(rate_key, window)
            await pipe2.execute()

            # Proceed with the request
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(max_requests)
            response.headers["X-RateLimit-Remaining"] = str(remaining - 1)
            response.headers["X-RateLimit-Reset"] = str(reset_time)
            return response

        except Exception as exc:
            # If Redis is unavailable, allow the request through
            logger.warning(
                "Rate limiter Redis error, allowing request: %s", exc
            )
            return await call_next(request)
