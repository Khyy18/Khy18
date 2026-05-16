"""Тесты rate limiter: token bucket + middleware."""

import time
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web

from rate_limiter.middleware import RateLimiterMiddleware, TokenBucket


class TestTokenBucket:
    """Тесты алгоритма Token Bucket."""

    def test_allows_within_capacity(self):
        """Разрешает запросы в пределах capacity."""
        bucket = TokenBucket(capacity=5, refill_rate=1.0)
        for _ in range(5):
            assert bucket.consume() is True

    def test_rejects_when_empty(self):
        """Отклоняет когда бакет пустой."""
        bucket = TokenBucket(capacity=2, refill_rate=0.0)
        assert bucket.consume() is True
        assert bucket.consume() is True
        # Бакет пуст
        assert bucket.consume() is False

    def test_refills_over_time(self):
        """Бакет пополняется со временем."""
        bucket = TokenBucket(capacity=2, refill_rate=10.0)
        # Опустошаем бакет
        bucket.consume()
        bucket.consume()
        assert bucket.consume() is False

        # Имитируем прошествие 0.5 секунды (refill_rate=10, т.е. 5 токенов)
        bucket.last_refill -= 0.5
        assert bucket.consume() is True

    def test_does_not_exceed_capacity(self):
        """Токены не накапливаются выше capacity."""
        bucket = TokenBucket(capacity=3, refill_rate=100.0)
        # Ждём "долго" (имитация)
        bucket.last_refill -= 100
        # После пополнения не больше capacity
        assert bucket.consume() is True
        assert bucket.consume() is True
        assert bucket.consume() is True
        assert bucket.consume() is False


class TestRateLimiterMiddleware:
    """Тесты aiohttp middleware для rate limiting."""

    @pytest.fixture
    def limiter_app(self):
        """Создать приложение с rate limiter middleware."""
        app = web.Application()
        rate_limiter = RateLimiterMiddleware(capacity=3, refill_rate=0.0)
        app.middlewares.append(rate_limiter.middleware)

        async def ok_handler(request):
            return web.Response(text="ok")

        app.router.add_get("/test", ok_handler)
        return app

    @pytest.mark.asyncio
    async def test_allows_within_limit(self, aiohttp_client, limiter_app):
        """Пропускает запросы в пределах лимита."""
        client = await aiohttp_client(limiter_app)
        for _ in range(3):
            resp = await client.get("/test")
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_returns_429_when_exceeded(self, aiohttp_client, limiter_app):
        """Возвращает 429 при превышении лимита."""
        client = await aiohttp_client(limiter_app)
        # Исчерпываем лимит
        for _ in range(3):
            await client.get("/test")
        # Следующий запрос должен получить 429
        resp = await client.get("/test")
        assert resp.status == 429
        data = await resp.json()
        assert "error" in data

    @pytest.mark.asyncio
    async def test_different_ips_independent(self):
        """Разные IP имеют независимые бакеты."""
        limiter = RateLimiterMiddleware(capacity=1, refill_rate=0.0)
        bucket_a = limiter._get_bucket("1.2.3.4")
        bucket_b = limiter._get_bucket("5.6.7.8")

        assert bucket_a.consume() is True
        # bucket_b не затронут
        assert bucket_b.consume() is True
