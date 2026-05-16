"""Tests for TTL-based rate cache."""

import time

import pytest

from services.rate_cache import RateCache


class TestRateCache:
    """Test suite for RateCache."""

    def test_cache_hit_within_ttl(self):
        """Test that cached data is returned within TTL window."""
        cache = RateCache(ttl=60)
        data = {"toAmount": 15.0, "provider": "changenow"}

        cache.set("btc", "eth", 1.0, "standard", data)
        result = cache.get("btc", "eth", 1.0, "standard")

        assert result == data
        assert result["toAmount"] == 15.0

    def test_cache_miss_after_ttl_expiry(self):
        """Test that expired entries return None."""
        cache = RateCache(ttl=2)
        data = {"toAmount": 15.0}

        cache.set("btc", "eth", 1.0, "standard", data)

        # Manually set the timestamp to be older than TTL
        cache._cache["btc:eth:1.0:standard"] = (time.time() - 3, data)

        # Now get should see it as expired and return None
        result = cache.get("btc", "eth", 1.0, "standard")

        assert result is None

    def test_cache_miss_for_unknown_key(self):
        """Test that unknown keys return None."""
        cache = RateCache(ttl=60)
        result = cache.get("btc", "eth", 1.0, "standard")
        assert result is None

    def test_cache_invalidation(self):
        """Test that invalidate removes specific cache entry."""
        cache = RateCache(ttl=60)
        data = {"toAmount": 15.0}

        cache.set("btc", "eth", 1.0, "standard", data)
        assert cache.get("btc", "eth", 1.0, "standard") is not None

        cache.invalidate("btc", "eth", 1.0, "standard")
        assert cache.get("btc", "eth", 1.0, "standard") is None

    def test_cache_clear(self):
        """Test that clear removes all entries."""
        cache = RateCache(ttl=60)
        cache.set("btc", "eth", 1.0, "standard", {"a": 1})
        cache.set("eth", "usdt", 2.0, "fixed-rate", {"b": 2})

        assert cache.get("btc", "eth", 1.0, "standard") is not None
        assert cache.get("eth", "usdt", 2.0, "fixed-rate") is not None

        cache.clear()

        assert cache.get("btc", "eth", 1.0, "standard") is None
        assert cache.get("eth", "usdt", 2.0, "fixed-rate") is None

    def test_different_amounts_different_keys(self):
        """Test that different amounts produce different cache keys."""
        cache = RateCache(ttl=60)
        cache.set("btc", "eth", 1.0, "standard", {"toAmount": 15.0})
        cache.set("btc", "eth", 2.0, "standard", {"toAmount": 30.0})

        result1 = cache.get("btc", "eth", 1.0, "standard")
        result2 = cache.get("btc", "eth", 2.0, "standard")

        assert result1["toAmount"] == 15.0
        assert result2["toAmount"] == 30.0

    def test_different_flows_different_keys(self):
        """Test that different flow types produce different cache keys."""
        cache = RateCache(ttl=60)
        cache.set("btc", "eth", 1.0, "standard", {"provider": "cn"})
        cache.set("btc", "eth", 1.0, "fixed-rate", {"provider": "ex"})

        result_standard = cache.get("btc", "eth", 1.0, "standard")
        result_fixed = cache.get("btc", "eth", 1.0, "fixed-rate")

        assert result_standard["provider"] == "cn"
        assert result_fixed["provider"] == "ex"

    def test_case_insensitive_keys(self):
        """Test that currency tickers are case-insensitive in cache keys."""
        cache = RateCache(ttl=60)
        cache.set("BTC", "ETH", 1.0, "standard", {"toAmount": 15.0})

        # Should find it with lowercase
        result = cache.get("btc", "eth", 1.0, "standard")
        assert result is not None
        assert result["toAmount"] == 15.0

    def test_cleanup_removes_expired_entries(self):
        """Test that cleanup removes only expired entries."""
        cache = RateCache(ttl=5)

        # Add one fresh and one expired entry
        cache.set("btc", "eth", 1.0, "standard", {"fresh": True})
        # Manually insert an expired entry
        cache._cache["old:key:1.0:standard"] = (time.time() - 10, {"old": True})

        cache.cleanup()

        # Fresh entry should remain
        assert cache.get("btc", "eth", 1.0, "standard") is not None
        # Expired entry should be gone
        assert "old:key:1.0:standard" not in cache._cache

    def test_invalidate_nonexistent_key_no_error(self):
        """Test that invalidating a non-existent key does not raise."""
        cache = RateCache(ttl=60)
        # Should not raise
        cache.invalidate("nonexistent", "pair", 999.0, "standard")
