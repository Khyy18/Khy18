"""Тесты для Redis cache с graceful fallback."""

import pytest

from ai_office.core.cache import AsyncRedisCache, cached


@pytest.mark.asyncio
async def test_cache_no_redis():
    """Cache возвращает None и set - no-op когда Redis не подключен."""
    cache = AsyncRedisCache()
    # Not connected, should be no-op
    result = await cache.get("test_key")
    assert result is None

    # Should not raise
    await cache.set("test_key", "value", ttl=10)
    await cache.delete("test_key")
    await cache.invalidate_pattern("test_*")


@pytest.mark.asyncio
async def test_cached_decorator():
    """Декоратор @cached вызывает функцию при промахе и работает как no-op без Redis."""
    call_count = 0

    @cached(ttl=5, key_prefix="test")
    async def my_function(x=1):
        nonlocal call_count
        call_count += 1
        return {"result": x}

    # First call - function should be invoked
    result1 = await my_function(x=1)
    assert result1 == {"result": 1}
    assert call_count == 1

    # Second call - without Redis, function invoked again (no caching)
    result2 = await my_function(x=1)
    assert result2 == {"result": 1}
    assert call_count == 2


@pytest.mark.asyncio
async def test_cache_connect_without_url():
    """Cache connect gracefully handles missing URL."""
    cache = AsyncRedisCache()
    await cache.connect()  # Should not raise
    assert cache._available is False
    await cache.disconnect()
