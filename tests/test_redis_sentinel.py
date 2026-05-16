"""Tests for db/redis_cache.py Redis Sentinel support."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.redis_cache import RedisCache, RedisSentinelCache, get_redis_cache


class TestRedisSentinelCacheConstruction:
    def test_creates_with_sentinel_hosts(self) -> None:
        hosts = [("sentinel1", 26379), ("sentinel2", 26379)]
        cache = RedisSentinelCache(sentinel_hosts=hosts, master_name="mymaster")
        assert cache._sentinel_hosts == hosts
        assert cache._master_name == "mymaster"
        assert cache._client is None

    @pytest.mark.asyncio
    async def test_connect_creates_sentinel_and_master(self) -> None:
        hosts = [("sentinel1", 26379)]
        cache = RedisSentinelCache(sentinel_hosts=hosts, master_name="testmaster")

        mock_sentinel_instance = MagicMock()
        mock_master = AsyncMock()
        mock_sentinel_instance.master_for.return_value = mock_master

        with patch("db.redis_cache.Sentinel", return_value=mock_sentinel_instance) as mock_cls:
            await cache.connect()
            mock_cls.assert_called_once_with(hosts, decode_responses=True)
            mock_sentinel_instance.master_for.assert_called_once_with("testmaster")
            assert cache._client is mock_master

    @pytest.mark.asyncio
    async def test_get_proxies_to_master(self) -> None:
        cache = RedisSentinelCache(sentinel_hosts=[("h", 26379)])
        mock_client = AsyncMock()
        mock_client.get.return_value = '{"key": "value"}'
        cache._client = mock_client

        result = await cache.get("test_key")
        mock_client.get.assert_called_once_with("test_key")
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_set_proxies_to_master(self) -> None:
        cache = RedisSentinelCache(sentinel_hosts=[("h", 26379)])
        mock_client = AsyncMock()
        cache._client = mock_client

        await cache.set("k", {"data": 1}, ttl=60)
        mock_client.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_proxies_to_master(self) -> None:
        cache = RedisSentinelCache(sentinel_hosts=[("h", 26379)])
        mock_client = AsyncMock()
        cache._client = mock_client

        await cache.delete("k")
        mock_client.delete.assert_called_once_with("k")

    @pytest.mark.asyncio
    async def test_get_returns_default_when_no_client(self) -> None:
        cache = RedisSentinelCache(sentinel_hosts=[("h", 26379)])
        result = await cache.get("k", default="fallback")
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_close_cleans_up(self) -> None:
        cache = RedisSentinelCache(sentinel_hosts=[("h", 26379)])
        mock_client = AsyncMock()
        cache._client = mock_client
        mock_sentinel = MagicMock()
        mock_sentinel.close = AsyncMock()
        cache._sentinel = mock_sentinel

        await cache.close()
        mock_client.aclose.assert_called_once()
        assert cache._client is None
        assert cache._sentinel is None


class TestGetRedisCacheFactory:
    def test_returns_sentinel_cache_when_hosts_provided(self) -> None:
        hosts = [("sentinel1", 26379), ("sentinel2", 26379)]
        cache = get_redis_cache(
            url="redis://localhost",
            sentinel_hosts=hosts,
            sentinel_master="mymaster",
        )
        assert isinstance(cache, RedisSentinelCache)

    def test_returns_standard_cache_when_no_sentinel(self) -> None:
        cache = get_redis_cache(url="redis://localhost:6379")
        assert isinstance(cache, RedisCache)

    def test_returns_standard_cache_with_empty_sentinel_list(self) -> None:
        cache = get_redis_cache(url="redis://localhost:6379", sentinel_hosts=[])
        assert isinstance(cache, RedisCache)

    def test_returns_standard_cache_with_none_sentinel(self) -> None:
        cache = get_redis_cache(url="redis://localhost:6379", sentinel_hosts=None)
        assert isinstance(cache, RedisCache)
