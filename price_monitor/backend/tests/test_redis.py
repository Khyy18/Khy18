"""Tests for Redis client graceful degradation."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import app.db.redis_client as redis_module
from app.db.redis_client import cache_get, cache_set, get_redis
from app.services.cache_service import cache_service


@pytest.fixture(autouse=True)
def reset_redis_state():
    """Reset redis module state before each test."""
    original_pool = redis_module._pool
    original_available = redis_module.redis_available
    original_last_retry = redis_module._last_retry_time

    redis_module._pool = None
    redis_module.redis_available = True
    redis_module._last_retry_time = 0.0

    yield

    redis_module._pool = original_pool
    redis_module.redis_available = original_available
    redis_module._last_retry_time = original_last_retry


class TestGetRedis:
    """Tests for get_redis function."""

    async def test_connection_failure_sets_unavailable(self):
        """When redis connection fails, redis_available becomes False."""
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("refused"))

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            result = await get_redis()

        assert result is None
        assert redis_module.redis_available is False

    async def test_returns_none_when_unavailable_and_retry_not_due(self):
        """get_redis returns None immediately if unavailable and retry interval not elapsed."""
        import time
        redis_module.redis_available = False
        redis_module._last_retry_time = time.time()  # just retried

        result = await get_redis()
        assert result is None


class TestCacheGetGracefulDegradation:
    """Tests for cache_get when Redis is unavailable."""

    async def test_cache_get_returns_none_when_unavailable(self):
        """cache_get returns None when redis_available is False."""
        redis_module.redis_available = False
        result = await cache_get("some_key")
        assert result is None

    async def test_cache_get_returns_none_on_connection_error(self):
        """cache_get returns None if get_redis returns None."""
        # Simulate get_redis returning None
        with patch("app.db.redis_client.get_redis", new_callable=AsyncMock, return_value=None):
            redis_module.redis_available = True
            redis_module._pool = None
            # Force get_redis path to fail
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(side_effect=ConnectionError("refused"))
            with patch("redis.asyncio.from_url", return_value=mock_redis):
                result = await cache_get("key")
            assert result is None


class TestCacheSetGracefulDegradation:
    """Tests for cache_set when Redis is unavailable."""

    async def test_cache_set_does_nothing_when_unavailable(self):
        """cache_set silently returns when redis_available is False."""
        redis_module.redis_available = False
        # Should not raise
        await cache_set("key", {"data": "value"}, ttl=60)

    async def test_cache_set_handles_error_gracefully(self):
        """cache_set catches exceptions and does not propagate."""
        redis_module.redis_available = True
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=Exception("write error"))

        with patch("redis.asyncio.from_url", return_value=mock_redis):
            redis_module._pool = mock_redis
            # Should not raise
            await cache_set("key", "val", ttl=10)


class TestCacheService:
    """Tests for CacheService wrapper."""

    async def test_cache_service_get_returns_none_when_unavailable(self):
        """cache_service.get returns None when Redis is unavailable."""
        redis_module.redis_available = False
        result = await cache_service.get("test_key")
        assert result is None

    async def test_cache_service_set_does_nothing_when_unavailable(self):
        """cache_service.set silently returns when Redis is unavailable."""
        redis_module.redis_available = False
        # Should not raise
        await cache_service.set("key", "value", ttl=60)
