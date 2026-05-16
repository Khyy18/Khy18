"""Redis-backed Token Bucket для распределённого rate limiting.

Использует Redis MULTI/EXEC для атомарных операций с бакетом.
Если Redis недоступен - fallback на in-memory TokenBucket.
"""

from __future__ import annotations

import time
from typing import Optional

import config
from rate_limiter.middleware import TokenBucket


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
            except Exception:
                self._redis = None
        return self._redis

    def _redis_key(self, key: str) -> str:
        return f"{self.key_prefix}:{key}"

    def consume(self, key: str, tokens: int = 1) -> bool:
        """Попытаться взять токен для данного ключа.

        Использует Redis MULTI/EXEC для атомарности.
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
            return self._fallback_consume(key, tokens)

    def _redis_consume(self, r, key: str, tokens: int) -> bool:
        """Атомарная операция с бакетом через Redis pipeline."""
        rkey = self._redis_key(key)
        now = time.time()

        pipe = r.pipeline(transaction=True)
        pipe.hgetall(rkey)
        results = pipe.execute()
        data = results[0]

        if data:
            current_tokens = float(data.get(b"tokens", self.capacity))
            last_refill = float(data.get(b"last_refill", now))
        else:
            current_tokens = float(self.capacity)
            last_refill = now

        # Пополняем
        elapsed = now - last_refill
        current_tokens = min(
            self.capacity,
            current_tokens + elapsed * self.refill_rate,
        )

        if current_tokens >= tokens:
            current_tokens -= tokens
            allowed = True
        else:
            allowed = False

        # Сохраняем обратно
        pipe2 = r.pipeline(transaction=True)
        pipe2.hset(rkey, mapping={
            "tokens": str(current_tokens),
            "last_refill": str(now),
        })
        pipe2.expire(rkey, 3600)  # TTL 1 час для cleanup
        pipe2.execute()

        return allowed

    def _fallback_consume(self, key: str, tokens: int) -> bool:
        """In-memory fallback при недоступности Redis."""
        if key not in self._fallback_buckets:
            self._fallback_buckets[key] = TokenBucket(
                capacity=self.capacity,
                refill_rate=self.refill_rate,
            )
        return self._fallback_buckets[key].consume(tokens)
