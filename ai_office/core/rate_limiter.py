"""Rate limiter и бюджетный контроль для LLM вызовов."""

import asyncio
import logging
import time
from datetime import date, datetime, timezone
from enum import IntEnum
from typing import Optional

from ai_office.core.config import settings

logger = logging.getLogger(__name__)


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
    """Отслеживание дневного бюджета на LLM вызовы.

    On initialization (or first access each day), hydrates _today_spend
    from the token_usage table to survive process restarts.
    """

    def __init__(self, daily_budget_usd: float = 10.0, time_func=None):
        self.daily_budget_usd = daily_budget_usd
        self._time_func = time_func
        self._today_spend: float = 0.0
        self._current_date: Optional[date] = None
        self._lock = asyncio.Lock()
        self._hydrated: bool = False

    def _get_today(self) -> date:
        """Get current UTC date."""
        if self._time_func:
            return datetime.fromtimestamp(self._time_func(), tz=timezone.utc).date()
        return datetime.now(timezone.utc).date()

    async def _hydrate_from_db(self) -> None:
        """Load today's spend from token_usage table to survive restarts."""
        try:
            from ai_office.core.database import async_session
            from ai_office.core.models import TokenUsage
            from sqlalchemy import select, func

            today = self._get_today()
            today_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)

            async with async_session() as session:
                result = await session.execute(
                    select(func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0.0))
                    .where(TokenUsage.timestamp >= today_start)
                )
                self._today_spend = float(result.scalar())
                self._current_date = today
                self._hydrated = True
                logger.info(
                    "Budget tracker hydrated from DB: $%.4f spent today",
                    self._today_spend,
                )
        except Exception as e:
            # If DB is unavailable (e.g. in tests), reset to zero for the new day
            logger.warning("Could not hydrate budget from DB: %s", str(e))
            self._today_spend = 0.0
            self._current_date = self._get_today()
            self._hydrated = True

    async def _reset_if_new_day(self):
        """Reset spend counter at midnight UTC, hydrating from DB."""
        today = self._get_today()
        if self._current_date != today:
            # New day (or first access) - try to hydrate from DB
            await self._hydrate_from_db()

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
