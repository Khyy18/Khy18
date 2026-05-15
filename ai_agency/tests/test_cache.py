"""Tests for cache module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import cache


@pytest.mark.asyncio
class TestCache:
    """Tests for semantic cache module."""

    async def test_cache_key_deterministic(self, initialized_db):
        """cache_key produces deterministic hash."""
        key1 = cache.cache_key("rewrite", "Hello World")
        key2 = cache.cache_key("rewrite", "Hello World")
        assert key1 == key2
        assert len(key1) == 64  # SHA256 hex length

    async def test_cache_key_normalized(self, initialized_db):
        """cache_key normalizes input (lowercase + strip)."""
        key1 = cache.cache_key("rewrite", "Hello World")
        key2 = cache.cache_key("rewrite", "  HELLO WORLD  ")
        assert key1 == key2

    async def test_store_and_get_cached_result(self, initialized_db):
        """store_result and get_cached_result work together."""
        # Reset counters
        cache._cache_hits = 0
        cache._cache_misses = 0

        await cache.store_result("rewrite", "test input", "cached output")

        result = await cache.get_cached_result("rewrite", "test input")
        assert result == "cached output"
        assert cache._cache_hits == 1

    async def test_cache_miss(self, initialized_db):
        """get_cached_result returns None on miss."""
        cache._cache_hits = 0
        cache._cache_misses = 0

        result = await cache.get_cached_result("rewrite", "nonexistent input")
        assert result is None
        assert cache._cache_misses == 1

    async def test_cache_stats(self, initialized_db):
        """get_cache_stats returns correct statistics."""
        cache._cache_hits = 0
        cache._cache_misses = 0

        await cache.store_result("summary", "input1", "output1")
        await cache.get_cached_result("summary", "input1")  # hit
        await cache.get_cached_result("summary", "input2")  # miss

        stats = await cache.get_cache_stats()
        assert stats["session_hits"] == 1
        assert stats["session_misses"] == 1
        assert stats["session_hit_rate"] == 50.0
        assert stats["total_entries"] >= 1

    async def test_cache_different_services(self, initialized_db):
        """Cache entries are separated by service_type."""
        await cache.store_result("rewrite", "same input", "rewrite output")
        await cache.store_result("copywriting", "same input", "copy output")

        result1 = await cache.get_cached_result("rewrite", "same input")
        result2 = await cache.get_cached_result("copywriting", "same input")
        assert result1 == "rewrite output"
        assert result2 == "copy output"

    async def test_cleanup_expired(self, initialized_db):
        """cleanup_expired removes old entries."""
        import aiosqlite
        from datetime import datetime, timedelta

        # Insert an expired entry manually
        expired = (datetime.utcnow() - timedelta(days=1)).isoformat()
        async with aiosqlite.connect(initialized_db.DATABASE_PATH) as db:
            await db.execute(
                """INSERT INTO semantic_cache
                   (service_type, input_hash, result_text, expires_at)
                   VALUES (?, ?, ?, ?)""",
                ("test", "expired_hash", "old result", expired),
            )
            await db.commit()

        removed = await cache.cleanup_expired()
        assert removed >= 1
