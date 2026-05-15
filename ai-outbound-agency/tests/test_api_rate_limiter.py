"""Tests for the API rate limiter middleware."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.api_rate_limiter import (
    RateLimiterMiddleware,
    ENDPOINT_GROUPS,
    AUTHENTICATED_LIMIT,
    UNAUTHENTICATED_LIMIT,
    DEFAULT_WINDOW,
)


def _make_request(path: str = "/api/leads", authenticated: bool = False, client_ip: str = "192.168.1.1"):
    """Create a mock Starlette request object."""
    request = MagicMock()
    request.url.path = path
    request.headers = {}
    request.client = MagicMock()
    request.client.host = client_ip

    if authenticated:
        user = MagicMock()
        user.id = "user-123"
        request.state.user = user
    else:
        request.state = MagicMock(spec=[])
    return request


def _make_response(status_code: int = 200):
    """Create a mock response with mutable headers."""
    response = MagicMock()
    response.status_code = status_code
    response.headers = {}
    return response


@pytest.fixture
def rate_limiter_middleware():
    """Create a RateLimiterMiddleware instance with mocked app."""
    app = MagicMock()
    middleware = RateLimiterMiddleware(app, redis_url="redis://localhost:6379/0")
    return middleware


class TestRateLimiterMiddleware:
    """Tests for RateLimiterMiddleware."""

    @pytest.mark.asyncio
    async def test_rate_limit_allows_under_limit(self, mock_redis):
        """Test that requests under the rate limit are allowed through."""
        app = MagicMock()
        middleware = RateLimiterMiddleware(app, redis_url="redis://localhost:6379/0")
        middleware._redis = mock_redis

        # Pipeline returns: zremrangebyscore result, zcard result (0 existing)
        pipe_mock = AsyncMock()
        pipe_mock.zremrangebyscore = MagicMock(return_value=pipe_mock)
        pipe_mock.zcard = MagicMock(return_value=pipe_mock)
        pipe_mock.execute = AsyncMock(return_value=[0, 5])  # 5 requests in window

        pipe_mock2 = AsyncMock()
        pipe_mock2.zadd = MagicMock(return_value=pipe_mock2)
        pipe_mock2.expire = MagicMock(return_value=pipe_mock2)
        pipe_mock2.execute = AsyncMock(return_value=[1, True])

        call_count = [0]

        def make_pipe():
            call_count[0] += 1
            if call_count[0] == 1:
                return pipe_mock
            return pipe_mock2

        mock_redis.pipeline = MagicMock(side_effect=make_pipe)

        request = _make_request("/api/leads", authenticated=True)

        response_mock = _make_response()
        call_next = AsyncMock(return_value=response_mock)

        response = await middleware.dispatch(request, call_next)

        # Request should be forwarded
        call_next.assert_awaited_once()
        assert response.headers["X-RateLimit-Remaining"] is not None

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_over_limit(self, mock_redis):
        """Test that requests over the rate limit are blocked with 429."""
        app = MagicMock()
        middleware = RateLimiterMiddleware(app, redis_url="redis://localhost:6379/0")
        middleware._redis = mock_redis

        # Pipeline returns count at limit (100 for authenticated)
        pipe_mock = AsyncMock()
        pipe_mock.zremrangebyscore = MagicMock(return_value=pipe_mock)
        pipe_mock.zcard = MagicMock(return_value=pipe_mock)
        pipe_mock.execute = AsyncMock(return_value=[0, 100])  # At limit

        mock_redis.pipeline = MagicMock(return_value=pipe_mock)

        request = _make_request("/api/leads", authenticated=True)
        call_next = AsyncMock()

        response = await middleware.dispatch(request, call_next)

        # Request should NOT be forwarded
        call_next.assert_not_awaited()
        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_rate_limit_returns_429_with_retry_after(self, mock_redis):
        """Test that 429 response includes Retry-After header."""
        app = MagicMock()
        middleware = RateLimiterMiddleware(app, redis_url="redis://localhost:6379/0")
        middleware._redis = mock_redis

        pipe_mock = AsyncMock()
        pipe_mock.zremrangebyscore = MagicMock(return_value=pipe_mock)
        pipe_mock.zcard = MagicMock(return_value=pipe_mock)
        pipe_mock.execute = AsyncMock(return_value=[0, 100])  # At limit

        mock_redis.pipeline = MagicMock(return_value=pipe_mock)

        request = _make_request("/api/leads", authenticated=True)
        call_next = AsyncMock()

        response = await middleware.dispatch(request, call_next)

        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert int(response.headers["Retry-After"]) > 0

    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(self, mock_redis):
        """Test that rate limit headers are added to successful responses."""
        app = MagicMock()
        middleware = RateLimiterMiddleware(app, redis_url="redis://localhost:6379/0")
        middleware._redis = mock_redis

        # Under limit
        pipe_mock = AsyncMock()
        pipe_mock.zremrangebyscore = MagicMock(return_value=pipe_mock)
        pipe_mock.zcard = MagicMock(return_value=pipe_mock)
        pipe_mock.execute = AsyncMock(return_value=[0, 10])

        pipe_mock2 = AsyncMock()
        pipe_mock2.zadd = MagicMock(return_value=pipe_mock2)
        pipe_mock2.expire = MagicMock(return_value=pipe_mock2)
        pipe_mock2.execute = AsyncMock(return_value=[1, True])

        call_count = [0]

        def make_pipe():
            call_count[0] += 1
            if call_count[0] == 1:
                return pipe_mock
            return pipe_mock2

        mock_redis.pipeline = MagicMock(side_effect=make_pipe)

        request = _make_request("/api/leads", authenticated=True)
        response_mock = _make_response()
        call_next = AsyncMock(return_value=response_mock)

        response = await middleware.dispatch(request, call_next)

        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    @pytest.mark.asyncio
    async def test_auth_endpoints_have_lower_limit(self, mock_redis):
        """Test that /api/auth/* endpoints have a limit of 5/min."""
        app = MagicMock()
        middleware = RateLimiterMiddleware(app, redis_url="redis://localhost:6379/0")
        middleware._redis = mock_redis

        # Simulate 5 requests already (at limit for auth)
        pipe_mock = AsyncMock()
        pipe_mock.zremrangebyscore = MagicMock(return_value=pipe_mock)
        pipe_mock.zcard = MagicMock(return_value=pipe_mock)
        pipe_mock.execute = AsyncMock(return_value=[0, 5])  # At auth limit

        mock_redis.pipeline = MagicMock(return_value=pipe_mock)

        request = _make_request("/api/auth/login", authenticated=False)
        call_next = AsyncMock()

        response = await middleware.dispatch(request, call_next)

        # Should be blocked at 5 requests for auth endpoints
        assert response.status_code == 429
        call_next.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_webhook_endpoints_have_higher_limit(self, mock_redis):
        """Test that /webhooks/* endpoints have a limit of 1000/min."""
        app = MagicMock()
        middleware = RateLimiterMiddleware(app, redis_url="redis://localhost:6379/0")
        middleware._redis = mock_redis

        # Simulate 500 requests (under webhook limit of 1000)
        pipe_mock = AsyncMock()
        pipe_mock.zremrangebyscore = MagicMock(return_value=pipe_mock)
        pipe_mock.zcard = MagicMock(return_value=pipe_mock)
        pipe_mock.execute = AsyncMock(return_value=[0, 500])

        pipe_mock2 = AsyncMock()
        pipe_mock2.zadd = MagicMock(return_value=pipe_mock2)
        pipe_mock2.expire = MagicMock(return_value=pipe_mock2)
        pipe_mock2.execute = AsyncMock(return_value=[1, True])

        call_count = [0]

        def make_pipe():
            call_count[0] += 1
            if call_count[0] == 1:
                return pipe_mock
            return pipe_mock2

        mock_redis.pipeline = MagicMock(side_effect=make_pipe)

        request = _make_request("/webhooks/reply", authenticated=False)
        response_mock = _make_response()
        call_next = AsyncMock(return_value=response_mock)

        response = await middleware.dispatch(request, call_next)

        # Should be allowed since 500 < 1000
        call_next.assert_awaited_once()
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_redis_unavailable_allows_request(self, mock_redis):
        """Test that requests are allowed through when Redis is unavailable."""
        app = MagicMock()
        middleware = RateLimiterMiddleware(app, redis_url="redis://localhost:6379/0")
        middleware._redis = mock_redis

        # Simulate Redis connection error
        pipe_mock = AsyncMock()
        pipe_mock.zremrangebyscore = MagicMock(return_value=pipe_mock)
        pipe_mock.zcard = MagicMock(return_value=pipe_mock)
        pipe_mock.execute = AsyncMock(side_effect=ConnectionError("Redis unavailable"))
        mock_redis.pipeline = MagicMock(return_value=pipe_mock)

        request = _make_request("/api/leads", authenticated=True)
        response_mock = _make_response()
        call_next = AsyncMock(return_value=response_mock)

        response = await middleware.dispatch(request, call_next)

        # Should allow request through despite Redis error
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_health_endpoint_not_rate_limited(self, mock_redis):
        """Test that /health endpoint is not subject to rate limiting."""
        app = MagicMock()
        middleware = RateLimiterMiddleware(app, redis_url="redis://localhost:6379/0")
        middleware._redis = mock_redis

        request = _make_request("/health", authenticated=False)
        response_mock = _make_response()
        call_next = AsyncMock(return_value=response_mock)

        response = await middleware.dispatch(request, call_next)

        # Should pass through without checking Redis
        call_next.assert_awaited_once()
        # Redis pipeline should not have been called
        mock_redis.pipeline.assert_not_called()
