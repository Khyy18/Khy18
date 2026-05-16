"""Token Bucket rate limiter + aiohttp middleware.

Реализует per-IP rate limiting на базе алгоритма Token Bucket.
"""

from __future__ import annotations

import time
from typing import Callable

from aiohttp import web

import config


class TokenBucket:
    """Реализация алгоритма Token Bucket (корзина токенов).

    capacity - максимальное число токенов (burst).
    refill_rate - скорость пополнения (токенов в секунду).
    """

    def __init__(self, capacity: int, refill_rate: float) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def consume(self, tokens: int = 1) -> bool:
        """Попытаться взять токен. Возвращает True если успешно."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate,
        )
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimiterMiddleware:
    """aiohttp middleware для rate limiting по IP-адресу."""

    def __init__(
        self,
        capacity: int | None = None,
        refill_rate: float | None = None,
    ) -> None:
        self.capacity = capacity if capacity is not None else config.RATE_LIMIT_BURST
        self.refill_rate = (
            refill_rate if refill_rate is not None else float(config.RATE_LIMIT_RPS)
        )
        self._buckets: dict[str, TokenBucket] = {}

    def _get_bucket(self, key: str) -> TokenBucket:
        """Получить или создать бакет для данного ключа (IP)."""
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(
                capacity=self.capacity,
                refill_rate=self.refill_rate,
            )
        return self._buckets[key]

    def _get_client_ip(self, request: web.Request) -> str:
        """Извлечь IP-адрес клиента из запроса."""
        # Пробуем X-Forwarded-For для reverse proxy
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        # Fallback: peer IP
        peername = request.transport.get_extra_info("peername")
        if peername:
            return peername[0]
        return "unknown"

    @web.middleware
    async def middleware(
        self,
        request: web.Request,
        handler: Callable,
    ) -> web.Response:
        """aiohttp middleware: проверяет бакет перед обработкой запроса."""
        client_ip = self._get_client_ip(request)
        bucket = self._get_bucket(client_ip)

        if not bucket.consume():
            return web.json_response(
                {"error": "Too Many Requests"},
                status=429,
            )

        return await handler(request)
