from __future__ import annotations

import json
import logging
import time
from datetime import date
from typing import Any

import redis.asyncio as aioredis

from core.config import Settings

logger = logging.getLogger(__name__)

# Daily limits per action type
DEFAULT_DAILY_LIMITS: dict[str, int] = {
    "connection_request": 25,
    "profile_view": 50,
    "message": 20,
}


class SessionPool:
    """Redis-based LinkedIn account pool with daily limits, cooldowns, and health monitoring."""

    def __init__(self, redis_url: str, settings: Settings) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._settings = settings
        self._accounts: list[dict[str, Any]] = json.loads(settings.linkedin_proxy_list)
        self._current_index = 0
        self._daily_limits = {
            "connection_request": settings.linkedin_max_connections_per_day,
            "profile_view": settings.linkedin_max_profile_views_per_day,
            "message": settings.linkedin_max_messages_per_day,
        }

    def _key_last_used(self, account_id: str) -> str:
        return f"linkedin:account:{account_id}:last_used"

    def _key_actions(self, account_id: str, action_date: str) -> str:
        return f"linkedin:account:{account_id}:actions:{action_date}"

    def _key_status(self, account_id: str) -> str:
        return f"linkedin:account:{account_id}:status"

    async def get_available_account(self) -> dict[str, Any] | None:
        """Get next available account using round-robin, respecting cooldown periods."""
        if not self._accounts:
            logger.warning("No LinkedIn accounts configured")
            return None

        total = len(self._accounts)
        cooldown_seconds = self._settings.linkedin_min_action_cooldown_hours * 3600
        now = time.time()

        for _ in range(total):
            account = self._accounts[self._current_index % total]
            self._current_index = (self._current_index + 1) % total
            account_id = account.get("id", str(self._current_index))

            # Check account status
            status = await self._redis.get(self._key_status(account_id))
            if status in ("restricted", "banned"):
                logger.debug("Skipping account %s (status=%s)", account_id, status)
                continue

            # Check cooldown
            last_used = await self._redis.get(self._key_last_used(account_id))
            if last_used:
                elapsed = now - float(last_used)
                if elapsed < cooldown_seconds:
                    logger.debug(
                        "Skipping account %s (cooldown: %.0fs remaining)",
                        account_id,
                        cooldown_seconds - elapsed,
                    )
                    continue

            # Check daily limits for all action types
            today = date.today().isoformat()
            actions_key = self._key_actions(account_id, today)
            actions_raw = await self._redis.hgetall(actions_key)

            over_limit = False
            for action_type, limit in self._daily_limits.items():
                count = int(actions_raw.get(action_type, 0))
                if count >= limit:
                    over_limit = True
                    break

            if over_limit:
                logger.debug("Skipping account %s (daily limit reached)", account_id)
                continue

            logger.info("Selected account %s for next action", account_id)
            return account

        logger.warning("No available LinkedIn accounts (all at limit or in cooldown)")
        return None

    async def record_action(self, account_id: str, action_type: str) -> None:
        """Record an action for an account, incrementing the daily counter."""
        now = time.time()
        today = date.today().isoformat()
        actions_key = self._key_actions(account_id, today)

        pipe = self._redis.pipeline()
        pipe.set(self._key_last_used(account_id), str(now))
        pipe.hincrby(actions_key, action_type, 1)
        pipe.expire(actions_key, 86400 * 2)  # Expire after 2 days
        await pipe.execute()

        logger.info(
            "Recorded action '%s' for account %s", action_type, account_id
        )

    async def check_health(self, account_id: str) -> str:
        """Check account health status. Returns 'active', 'restricted', or 'banned'."""
        status = await self._redis.get(self._key_status(account_id))
        return status if status else "active"

    async def mark_restricted(self, account_id: str) -> None:
        """Mark an account as restricted."""
        await self._redis.set(self._key_status(account_id), "restricted")
        logger.warning("Account %s marked as restricted", account_id)

    async def get_account_stats(self, account_id: str) -> dict[str, Any]:
        """Get statistics for an account."""
        today = date.today().isoformat()
        actions_key = self._key_actions(account_id, today)

        pipe = self._redis.pipeline()
        pipe.get(self._key_last_used(account_id))
        pipe.hgetall(actions_key)
        pipe.get(self._key_status(account_id))
        results = await pipe.execute()

        last_used = results[0]
        actions_today = results[1] if results[1] else {}
        status = results[2] if results[2] else "active"

        return {
            "account_id": account_id,
            "last_used": float(last_used) if last_used else None,
            "actions_today": {k: int(v) for k, v in actions_today.items()},
            "status": status,
        }

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()
