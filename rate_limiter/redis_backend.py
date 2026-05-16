"""Redis-backed Token Bucket для распределённого rate limiting.

Использует Lua-скрипт для атомарных операций с бакетом (read + refill + consume
в одном EVALSHA). Если Redis недоступен - fallback на in-memory TokenBucket.
"""

from __future__ import annotations

import time
from typing import Optional

import config
from rate_limiter.middleware import TokenBucket

# Lua-скрипт: атомарно читает bucket state, пополняет, потребляет токен.
# KEYS[1] = bucket hash key
# ARGV[1] = capacity, ARGV[2] = refill_rate, ARGV[3] = now, ARGV[4] = tokens_to_consume, ARGV[5] = ttl
_LUA_CONSUME = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])
local ttl = tonumber(ARGV[5])

local current_tokens = tonumber(redis.call('hget', key, 'tokens') or capacity)
local last_refill = tonumber(redis.call('hget', key, 'last_refill') or now)

if current_tokens == nil then current_tokens = capacity end
if last_refill == nil then last_refill = now end

-- Refill
local elapsed = now - last_refill
current_tokens = math.min(capacity, current_tokens + elapsed * refill_rate)

local allowed = 0
if current_tokens >= requested then
    current_tokens = current_tokens - requested
    allowed = 1
end

-- Save state
redis.call('hset', key, 'tokens', tostring(current_tokens), 'last_refill', tostring(now))
redis.call('expire', key, ttl)

return allowed
"""


class RedisTokenBucket:
    """Распределённый Token Bucket на базе Redis.

    Хранит состояние бакета в Redis hash для каждого ключа (IP).
    При недоступности Redis - автоматический fallback на in-memory.
    """

    def __init__(
        self,
        capacity: int | None = None,
        refill_rate: float | None = None,
        key_prefix: str = "ratelimit",
    ) -> None:
        self.capacity = capacity if capacity is not None else config.RATE_LIMIT_BURST
        self.refill_rate = (
            refill_rate if refill_rate is not None else float(config.RATE_LIMIT_RPS)
        )
        self.key_prefix = key_prefix
        self._redis: Optional[object] = None
        self._lua_sha: Optional[str] = None
        self._fallback_buckets: dict[str, TokenBucket] = {}

    def _get_redis(self):
        """Получить Redis-клиент (ленивая инициализация)."""
        if self._redis is None:
            redis_url = config.REDIS_URL
            if not redis_url:
                return None
            try:
                import redis as redis_lib

                self._redis = redis_lib.from_url(
                    redis_url, socket_connect_timeout=2
                )
                self._redis.ping()
                # Загружаем Lua-скрипт
                self._lua_sha = self._redis.script_load(_LUA_CONSUME)
            except Exception:
                self._redis = None
                self._lua_sha = None
        return self._redis

    def _redis_key(self, key: str) -> str:
        return f"{self.key_prefix}:{key}"

    def consume(self, key: str, tokens: int = 1) -> bool:
        """Попытаться взять токен для данного ключа.

        Использует Lua-скрипт для атомарности (без TOCTOU race).
        При ошибке - fallback на in-memory.
        """
        r = self._get_redis()
        if r is None:
            return self._fallback_consume(key, tokens)

        try:
            return self._redis_consume(r, key, tokens)
        except Exception:
            # Redis упал - fallback
            self._redis = None
            self._lua_sha = None
            return self._fallback_consume(key, tokens)

    def _redis_consume(self, r, key: str, tokens: int) -> bool:
        """Атомарная операция с бакетом через Lua-скрипт (EVALSHA)."""
        rkey = self._redis_key(key)
        now = time.time()

        result = r.evalsha(
            self._lua_sha,
            1,  # numkeys
            rkey,
            str(self.capacity),
            str(self.refill_rate),
            str(now),
            str(tokens),
            str(3600),  # TTL 1 час
        )
        return int(result) == 1

    def _fallback_consume(self, key: str, tokens: int) -> bool:
        """In-memory fallback при недоступности Redis."""
        if key not in self._fallback_buckets:
            self._fallback_buckets[key] = TokenBucket(
                capacity=self.capacity,
                refill_rate=self.refill_rate,
            )
        return self._fallback_buckets[key].consume(tokens)
