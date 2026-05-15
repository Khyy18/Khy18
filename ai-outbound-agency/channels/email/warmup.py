import logging
from datetime import date, datetime
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Warmup schedule: day 1 starts at 5 emails, linear ramp to 50 by day 21
_WARMUP_START = 5
_WARMUP_END = 50
_WARMUP_DAYS = 21


class DomainWarmupManager:
    """Manages domain warmup schedules using Redis for state tracking."""

    def __init__(self, redis_url: str, domains: list[str] | None = None) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._domains = domains or []

    def _warmup_key(self, domain: str) -> str:
        return f"warmup:{domain}"

    async def start_warmup(self, domain: str) -> None:
        """Initialize warmup tracking for a new domain."""
        key = self._warmup_key(domain)
        today = date.today().isoformat()
        await self._redis.hset(key, mapping={
            "start_date": today,
            "sends_today": "0",
            "last_reset_date": today,
        })
        logger.info("Started warmup for domain %s on %s", domain, today)

    async def get_daily_limit(self, domain: str) -> int:
        """Calculate allowed daily sends based on warmup schedule.

        Formula: min(5 + (day * 2.14), 50) - linear ramp from 5 to 50 over 21 days.
        Day 1 = 5 emails, Day 21+ = 50 emails.
        """
        key = self._warmup_key(domain)
        start_date_str = await self._redis.hget(key, "start_date")
        if not start_date_str:
            return _WARMUP_START

        start_date = date.fromisoformat(start_date_str)
        days_elapsed = (date.today() - start_date).days
        day_number = max(days_elapsed, 0)

        # Linear ramp: 5 + day * (45/21) approx 2.14 per day
        ramp_rate = (_WARMUP_END - _WARMUP_START) / (_WARMUP_DAYS - 1)
        limit = _WARMUP_START + (day_number * ramp_rate)
        return int(min(limit, _WARMUP_END))

    async def is_warmed_up(self, domain: str) -> bool:
        """Check if domain has completed the warmup period (21+ days)."""
        key = self._warmup_key(domain)
        start_date_str = await self._redis.hget(key, "start_date")
        if not start_date_str:
            return False

        start_date = date.fromisoformat(start_date_str)
        days_elapsed = (date.today() - start_date).days
        return days_elapsed >= _WARMUP_DAYS

    async def record_warmup_send(self, domain: str) -> None:
        """Increment today's send counter, resetting if the date has changed."""
        key = self._warmup_key(domain)
        today = date.today().isoformat()

        last_reset = await self._redis.hget(key, "last_reset_date")
        if last_reset != today:
            await self._redis.hset(key, mapping={
                "sends_today": "1",
                "last_reset_date": today,
            })
        else:
            await self._redis.hincrby(key, "sends_today", 1)

    async def get_warmup_status(self) -> dict[str, Any]:
        """Return warmup status for all tracked domains."""
        status: dict[str, Any] = {}
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor=cursor, match="warmup:*", count=100
            )
            for key in keys:
                domain = key.replace("warmup:", "", 1)
                data = await self._redis.hgetall(key)
                start_date_str = data.get("start_date", "")
                days_elapsed = 0
                if start_date_str:
                    start_date = date.fromisoformat(start_date_str)
                    days_elapsed = (date.today() - start_date).days

                status[domain] = {
                    "start_date": start_date_str,
                    "days_elapsed": days_elapsed,
                    "sends_today": int(data.get("sends_today", 0)),
                    "daily_limit": await self.get_daily_limit(domain),
                    "is_warmed_up": days_elapsed >= _WARMUP_DAYS,
                }
            if cursor == 0:
                break

        return status

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()
