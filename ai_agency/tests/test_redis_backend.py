"""Tests for Redis backend: queue, cache, rate limiting, health check."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import redis_backend
from redis_backend import RedisBackend, get_redis


@pytest.fixture
def mock_redis():
    """Create a mock Redis instance."""
    r = AsyncMock()
    r.lpush = AsyncMock()
    r.rpop = AsyncMock()
    r.get = AsyncMock()
    r.set = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.zremrangebyscore = AsyncMock()
    r.zadd = AsyncMock()
    r.zcard = AsyncMock()
    r.expire = AsyncMock()
    r.pipeline = MagicMock()
    r.close = AsyncMock()
    return r


@pytest.fixture
def backend(mock_redis):
    """Create a RedisBackend with mocked Redis."""
    b = RedisBackend("redis://localhost:6379")
    b._redis = mock_redis
    return b


@pytest.mark.asyncio
class TestRedisBackend:

    async def test_enqueue_dequeue(self, backend, mock_redis):
        """enqueue pushes JSON and dequeue pops it."""
        data = {"task": "process", "id": 1}

        await backend.enqueue("orders", data)
        mock_redis.lpush.assert_called_once_with("orders", json.dumps(data))

        # Simulate dequeue
        mock_redis.rpop = AsyncMock(return_value=json.dumps(data))
        result = await backend.dequeue("orders")
        assert result == data

    async def test_cache_get_set(self, backend, mock_redis):
        """cache operations work with TTL."""
        await backend.cache_set("key1", "value1", ttl=600)
        mock_redis.set.assert_called_once_with("key1", "value1", ex=600)

        mock_redis.get = AsyncMock(return_value="value1")
        result = await backend.cache_get("key1")
        assert result == "value1"

    async def test_rate_limit_check_within_limit(self, backend, mock_redis):
        """rate_limit_check returns True when under limit."""
        pipe = AsyncMock()
        pipe.zremrangebyscore = AsyncMock()
        pipe.zadd = AsyncMock()
        pipe.zcard = AsyncMock()
        pipe.expire = AsyncMock()
        pipe.execute = AsyncMock(return_value=[None, None, 3, None])
        mock_redis.pipeline = MagicMock(return_value=pipe)

        result = await backend.rate_limit_check("user:123", max_count=5, window_seconds=3600)
        assert result is True

    async def test_rate_limit_check_exceeds_limit(self, backend, mock_redis):
        """rate_limit_check returns False when over limit."""
        pipe = AsyncMock()
        pipe.zremrangebyscore = AsyncMock()
        pipe.zadd = AsyncMock()
        pipe.zcard = AsyncMock()
        pipe.expire = AsyncMock()
        pipe.execute = AsyncMock(return_value=[None, None, 11, None])
        mock_redis.pipeline = MagicMock(return_value=pipe)

        result = await backend.rate_limit_check("user:123", max_count=10, window_seconds=3600)
        assert result is False

    async def test_health_check_when_connected(self, backend, mock_redis):
        """health_check returns True when ping succeeds."""
        mock_redis.ping = AsyncMock(return_value=True)
        result = await backend.health_check()
        assert result is True

    async def test_get_redis_returns_none_when_no_url(self, monkeypatch):
        """get_redis() returns None when backend is not initialized."""
        redis_backend._backend = None
        result = get_redis()
        assert result is None

    async def test_dequeue_empty_queue(self, backend, mock_redis):
        """dequeue returns None when queue is empty."""
        mock_redis.rpop = AsyncMock(return_value=None)
        result = await backend.dequeue("empty_queue")
        assert result is None

    async def test_not_connected_operations_noop(self):
        """Operations are no-op when redis is not connected."""
        b = RedisBackend("redis://localhost:6379")
        # _redis is None by default
        await b.enqueue("q", {"x": 1})  # Should not raise
        result = await b.dequeue("q")
        assert result is None
        assert await b.cache_get("k") is None
