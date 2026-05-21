"""Tests for Redis-based rate limiter."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.rate_limiter import RateLimiter, rate_limit


class TestRateLimiter:
    """Tests for the sliding window rate limiter."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client for rate limiter."""
        redis = AsyncMock()
        redis._sorted_sets = {}

        class MockPipeline:
            def __init__(self, store):
                self._store = store
                self._commands = []

            def zremrangebyscore(self, key, min_score, max_score):
                self._commands.append(("zremrangebyscore", key, min_score, max_score))

            def zcard(self, key):
                self._commands.append(("zcard", key))

            def zadd(self, key, mapping):
                self._commands.append(("zadd", key, mapping))

            def expire(self, key, ttl):
                self._commands.append(("expire", key, ttl))

            async def execute(self):
                results = []
                for cmd in self._commands:
                    if cmd[0] == "zremrangebyscore":
                        key, min_s, max_s = cmd[1], cmd[2], cmd[3]
                        if key in self._store:
                            self._store[key] = {
                                k: v
                                for k, v in self._store[key].items()
                                if not (min_s <= v <= max_s)
                            }
                        results.append(0)
                    elif cmd[0] == "zcard":
                        key = cmd[1]
                        results.append(len(self._store.get(key, {})))
                    elif cmd[0] == "zadd":
                        key, mapping = cmd[1], cmd[2]
                        if key not in self._store:
                            self._store[key] = {}
                        self._store[key].update(mapping)
                        results.append(1)
                    elif cmd[0] == "expire":
                        results.append(True)
                return results

        def make_pipeline():
            return MockPipeline(redis._sorted_sets)

        redis.pipeline = MagicMock(side_effect=make_pipeline)
        return redis

    @pytest.fixture
    def limiter(self, mock_redis):
        """Create a RateLimiter with mock Redis."""
        rl = RateLimiter(redis_client=mock_redis)
        return rl

    @pytest.mark.asyncio
    async def test_first_request_allowed(self, limiter):
        """Test that the first request is always allowed."""
        allowed = await limiter.check_rate_limit("test_endpoint", "user1", 5, 60)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_within_limit_allowed(self, limiter):
        """Test that requests within limit are allowed."""
        for i in range(4):
            allowed = await limiter.check_rate_limit("test_endpoint", "user1", 5, 60)
            assert allowed is True

    @pytest.mark.asyncio
    async def test_exceeds_limit_blocked(self, limiter):
        """Test that requests exceeding limit are blocked."""
        for i in range(5):
            await limiter.check_rate_limit("test_endpoint", "user1", 5, 60)

        # 6th request should be blocked
        allowed = await limiter.check_rate_limit("test_endpoint", "user1", 5, 60)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_different_users_independent(self, limiter):
        """Test that rate limits are per-user."""
        for i in range(5):
            await limiter.check_rate_limit("test_endpoint", "user1", 5, 60)

        # user2 should still be allowed
        allowed = await limiter.check_rate_limit("test_endpoint", "user2", 5, 60)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_different_endpoints_independent(self, limiter):
        """Test that rate limits are per-endpoint."""
        for i in range(5):
            await limiter.check_rate_limit("endpoint_a", "user1", 5, 60)

        # Different endpoint should still be allowed
        allowed = await limiter.check_rate_limit("endpoint_b", "user1", 5, 60)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_no_redis_allows_all(self):
        """Test that rate limiter with no Redis allows all requests."""
        limiter = RateLimiter(redis_client=None)
        for i in range(100):
            allowed = await limiter.check_rate_limit("test", "user1", 5, 60)
            assert allowed is True

    @pytest.mark.asyncio
    async def test_rate_limit_dependency_blocks(self):
        """Test the rate_limit FastAPI dependency raises HTTPException."""
        from fastapi import HTTPException

        mock_redis = AsyncMock()
        mock_redis._sorted_sets = {}

        class MockPipeline:
            def __init__(self):
                self._count = 0

            def zremrangebyscore(self, *args):
                pass

            def zcard(self, *args):
                pass

            def zadd(self, *args):
                pass

            def expire(self, *args):
                pass

            async def execute(self):
                # Simulate being over limit
                return [0, 10, 1, True]

        mock_redis.pipeline = MagicMock(return_value=MockPipeline())

        from app.rate_limiter import rate_limiter as global_limiter

        original_redis = global_limiter._redis
        global_limiter._redis = mock_redis

        try:
            dep = rate_limit("test", 5, 60)

            # Create mock request
            mock_request = MagicMock()
            mock_request.client = MagicMock()
            mock_request.client.host = "127.0.0.1"
            mock_request.state = MagicMock(spec=[])

            with pytest.raises(HTTPException) as exc_info:
                await dep(mock_request)
            assert exc_info.value.status_code == 429
        finally:
            global_limiter._redis = original_redis
