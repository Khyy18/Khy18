"""Redis-кэш (опциональный слой поверх основного хранилища).

Использует redis[hiredis] для быстрого кэширования часто запрашиваемых данных.
TTL поддерживается. Если Redis недоступен - операции молча пропускаются.
Поддержка Redis Sentinel для HA-кластеров.
"""

from __future__ import annotations

import json
from typing import Any, Optional

try:
    import redis.asyncio as aioredis
    from redis.asyncio.sentinel import Sentinel
except ImportError:
    aioredis = None  # type: ignore[assignment]
    Sentinel = None  # type: ignore[assignment,misc]


class RedisCache:
    """Async Redis-кэш с TTL-поддержкой."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: Optional[Any] = None

    async def connect(self) -> None:
        """Создать подключение к Redis."""
        if aioredis is None:
            raise ImportError("redis не установлен: pip install redis[hiredis]")
        self._client = aioredis.from_url(self._url, decode_responses=True)

    async def close(self) -> None:
        """Закрыть подключение."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get(self, key: str, default: Any = None) -> Any:
        """Получить значение из кэша. Возвращает default если ключ отсутствует."""
        if not self._client:
            return default
        try:
            val = await self._client.get(key)
            if val is None:
                return default
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return val
        except Exception:
            return default

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Записать значение в кэш. ttl - время жизни в секундах."""
        if not self._client:
            return
        try:
            payload = json.dumps(value, ensure_ascii=False, default=str)
            if ttl:
                await self._client.setex(key, ttl, payload)
            else:
                await self._client.set(key, payload)
        except Exception:
            pass

    async def delete(self, key: str) -> None:
        """Удалить ключ из кэша."""
        if not self._client:
            return
        try:
            await self._client.delete(key)
        except Exception:
            pass


class RedisSentinelCache:
    """Async Redis-кэш через Sentinel для HA-кластеров."""

    def __init__(
        self,
        sentinel_hosts: list[tuple[str, int]],
        master_name: str = "mymaster",
    ) -> None:
        self._sentinel_hosts = sentinel_hosts
        self._master_name = master_name
        self._sentinel: Optional[Any] = None
        self._client: Optional[Any] = None

    async def connect(self) -> None:
        """Создать Sentinel и получить master-клиент."""
        if Sentinel is None:
            raise ImportError("redis не установлен: pip install redis[hiredis]")
        self._sentinel = Sentinel(
            self._sentinel_hosts, decode_responses=True
        )
        self._client = self._sentinel.master_for(self._master_name)

    async def close(self) -> None:
        """Закрыть подключение к master и Sentinel."""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._sentinel:
            # Close sentinel connections if the close method is available
            if hasattr(self._sentinel, "close"):
                await self._sentinel.close()
            self._sentinel = None

    async def get(self, key: str, default: Any = None) -> Any:
        """Получить значение из кэша через master."""
        if not self._client:
            return default
        try:
            val = await self._client.get(key)
            if val is None:
                return default
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return val
        except Exception:
            return default

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Записать значение через master."""
        if not self._client:
            return
        try:
            payload = json.dumps(value, ensure_ascii=False, default=str)
            if ttl:
                await self._client.setex(key, ttl, payload)
            else:
                await self._client.set(key, payload)
        except Exception:
            pass

    async def delete(self, key: str) -> None:
        """Удалить ключ через master."""
        if not self._client:
            return
        try:
            await self._client.delete(key)
        except Exception:
            pass


def get_redis_cache(
    url: str = "",
    sentinel_hosts: Optional[list[tuple[str, int]]] = None,
    sentinel_master: str = "mymaster",
) -> RedisCache | RedisSentinelCache:
    """Фабрика: вернуть RedisSentinelCache если sentinel_hosts заданы, иначе RedisCache."""
    if sentinel_hosts:
        return RedisSentinelCache(
            sentinel_hosts=sentinel_hosts, master_name=sentinel_master
        )
    return RedisCache(url=url)

