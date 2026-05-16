"""Rate limiter и бюджетный контроль для LLM вызовов."""

import asyncio
import time
from datetime import date, datetime, timezone
from enum import IntEnum
from typing import Optional

from ai_office.core.config import settings


class Priority(IntEnum):
    """Приоритеты запросов к LLM."""

    URGENT = 1  # Прямое сообщение пользователя
    NORMAL = 2  # Делегирование
    LOW = 3  # Проактивные / по расписанию


class RateLimitedError(Exception):
    """Превышен лимит запросов."""

    pass


class BudgetExhaustedError(Exception):
    """Дневной бюджет исчерпан."""

    pass


class TokenBucketRateLimiter:
    """Token bucket rate limiter с глобальным и per-agent лимитами."""

    def __init__(
        self,
        global_rpm: int = 100,
        agent_rpm: int = 20,
        time_func=None,
    ):
        self.global_rpm = global_rpm
        self.agent_rpm = agent_rpm
        self._time_func = time_func or time.monotonic
        self._lock = asyncio.Lock()

        # Global bucket
        self._global_tokens: float = float(global_rpm)
        self._global_last_refill: float = self._time_func()

        # Per-agent buckets: {agent_name: (tokens, last_refill)}
        self._agent_buckets: dict[str, tuple[float, float]] = {}

    def _refill(self, tokens: float, last_refill: float, max_tokens: int) -> tuple[float, float]:
        """Refill tokens based on elapsed time."""
        now = self._time_func()
        elapsed = now - last_refill
        refill_rate = max_tokens / 60.0  # tokens per second
        new_tokens = min(float(max_tokens), tokens + elapsed * refill_rate)
        return new_tokens, now

    async def acquire(self, agent_name: str, priority: Priority = Priority.NORMAL) -> bool:
        """Попытка получить разрешение на вызов LLM.

        Returns:
            True если разрешено, иначе raises RateLimitedError.
        """
        async with self._lock:
            # Refill global bucket
            self._global_tokens, self._global_last_refill = self._refill(
                self._global_tokens, self._global_last_refill, self.global_rpm
            )

            # Refill agent bucket
            if agent_name in self._agent_buckets:
                agent_tokens, agent_last = self._agent_buckets[agent_name]
            else:
                agent_tokens = float(self.agent_rpm)
                agent_last = self._time_func()

            agent_tokens, agent_last = self._refill(agent_tokens, agent_last, self.agent_rpm)

            # Check global limit
            if self._global_tokens < 1.0:
                raise RateLimitedError(
                    f"Глобальный лимит {self.global_rpm} запросов/мин исчерпан"
                )

            # Check agent limit (URGENT bypasses agent limit)
            if priority != Priority.URGENT and agent_tokens < 1.0:
                raise RateLimitedError(
                    f"Лимит агента '{agent_name}' ({self.agent_rpm} запросов/мин) исчерпан"
                )

            # Consume tokens
            self._global_tokens -= 1.0
            if priority != Priority.URGENT:
                agent_tokens -= 1.0

            self._agent_buckets[agent_name] = (agent_tokens, agent_last)
            return True


class DailyBudgetTracker:
    """Отслеживание дневного бюджета на LLM вызовы."""

    def __init__(self, daily_budget_usd: float = 10.0, time_func=None):
        self.daily_budget_usd = daily_budget_usd
        self._time_func = time_func
        self._today_spend: float = 0.0
        self._current_date: Optional[date] = None
        self._lock = asyncio.Lock()

    def _get_today(self) -> date:
        """Get current UTC date."""
        if self._time_func:
            return datetime.fromtimestamp(self._time_func(), tz=timezone.utc).date()
        return datetime.now(timezone.utc).date()

    async def _reset_if_new_day(self):
        """Reset spend counter at midnight UTC."""
        today = self._get_today()
        if self._current_date != today:
            self._today_spend = 0.0
            self._current_date = today

    async def check_budget(self) -> bool:
        """Проверить, не исчерпан ли бюджет.

        Returns:
            True если бюджет доступен, иначе raises BudgetExhaustedError.
        """
        async with self._lock:
            await self._reset_if_new_day()
            if self._today_spend >= self.daily_budget_usd:
                raise BudgetExhaustedError(
                    f"Дневной бюджет ${self.daily_budget_usd:.2f} исчерпан. "
                    f"Потрачено: ${self._today_spend:.4f}"
                )
            return True

    async def add_spend(self, amount_usd: float):
        """Добавить расход."""
        async with self._lock:
            await self._reset_if_new_day()
            self._today_spend += amount_usd

    async def get_today_spend(self) -> float:
        """Получить сумму расходов за сегодня."""
        async with self._lock:
            await self._reset_if_new_day()
            return self._today_spend


# Module-level instances
rate_limiter = TokenBucketRateLimiter(
    global_rpm=settings.global_rpm_limit,
    agent_rpm=settings.agent_rpm_limit,
)

budget_tracker = DailyBudgetTracker(
    daily_budget_usd=settings.daily_budget_usd,
)
