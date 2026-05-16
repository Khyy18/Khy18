"""AI Rate Limiter - ограничитель частоты запросов к LLM.

Реализует алгоритм token bucket с приоритетными очередями.
Гарантирует не более AI_RATE_LIMIT_RPM запросов в минуту.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

from arbitrage.config import AI_RATE_LIMIT_RPM

# Приоритеты (меньше = выше приоритет)
PRIORITY_CRITICAL: str = "CRITICAL"
PRIORITY_HIGH: str = "HIGH"
PRIORITY_NORMAL: str = "NORMAL"
PRIORITY_LOW: str = "LOW"

_PRIORITY_ORDER: dict[str, int] = {
    PRIORITY_CRITICAL: 0,
    PRIORITY_HIGH: 1,
    PRIORITY_NORMAL: 2,
    PRIORITY_LOW: 3,
}


class AiRateLimiter:
    """Token bucket rate limiter для AI-запросов с приоритетами."""

    def __init__(self, rpm: int = AI_RATE_LIMIT_RPM, burst: int = 5) -> None:
        """Инициализация rate limiter.

        Args:
            rpm: максимум запросов в минуту.
            burst: размер burst (дополнительных токенов сверх равномерного потока).
        """
        self._rpm: int = rpm
        self._burst: int = burst
        self._lock: asyncio.Lock = asyncio.Lock()
        # Временные метки выполненных запросов за последнюю минуту
        self._requests: deque[float] = deque()
        # Очереди ожидания по приоритету
        self._waiters: dict[str, int] = {
            PRIORITY_CRITICAL: 0,
            PRIORITY_HIGH: 0,
            PRIORITY_NORMAL: 0,
            PRIORITY_LOW: 0,
        }
        # Статистика
        self._total_acquired: int = 0
        self._total_rejected: int = 0

    def _cleanup_old_requests(self) -> None:
        """Удаляет записи о запросах старше 60 секунд."""
        now = time.time()
        while self._requests and (now - self._requests[0]) > 60.0:
            self._requests.popleft()

    def _available_tokens(self) -> int:
        """Количество доступных токенов прямо сейчас."""
        self._cleanup_old_requests()
        used = len(self._requests)
        return max(0, self._rpm - used)

    async def acquire(self, priority: str = "NORMAL", timeout: float = 30.0) -> bool:
        """Получить разрешение на AI-запрос.

        Args:
            priority: уровень приоритета (CRITICAL, HIGH, NORMAL, LOW).
            timeout: максимальное время ожидания в секундах.

        Returns:
            True если токен получен, False если таймаут.
        """
        if priority not in _PRIORITY_ORDER:
            priority = PRIORITY_NORMAL

        self._waiters[priority] += 1
        deadline = time.time() + timeout

        try:
            while True:
                async with self._lock:
                    available = self._available_tokens()
                    if available > 0:
                        # Проверяем что нет ожидающих с более высоким приоритетом
                        my_order = _PRIORITY_ORDER[priority]
                        higher_waiting = sum(
                            count for p, count in self._waiters.items()
                            if _PRIORITY_ORDER[p] < my_order and count > 0
                        )
                        if higher_waiting == 0 or available > higher_waiting:
                            self._requests.append(time.time())
                            self._total_acquired += 1
                            return True

                # Проверяем таймаут
                remaining = deadline - time.time()
                if remaining <= 0:
                    self._total_rejected += 1
                    return False

                # Ожидаем перед следующей попыткой
                wait_time = min(60.0 / self._rpm, remaining, 1.0)
                await asyncio.sleep(wait_time)
        finally:
            self._waiters[priority] -= 1

    def get_stats(self) -> dict[str, Any]:
        """Статистика использования rate limiter.

        Returns:
            Словарь со статистикой: использованные/доступные токены,
            длина очередей, общее количество запросов.
        """
        self._cleanup_old_requests()
        used = len(self._requests)
        return {
            "rpm_limit": self._rpm,
            "used_tokens": used,
            "available_tokens": max(0, self._rpm - used),
            "queue_lengths": dict(self._waiters),
            "total_acquired": self._total_acquired,
            "total_rejected": self._total_rejected,
            "requests_last_minute": used,
        }
