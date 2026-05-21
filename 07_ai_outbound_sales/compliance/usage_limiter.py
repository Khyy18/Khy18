from __future__ import annotations
import json
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Lua script for atomic check-and-increment.
# Returns 1 if increment was allowed, 0 if limit would be exceeded.
# Args: KEYS[1] = usage key, ARGV[1] = limit, ARGV[2] = amount, ARGV[3] = TTL seconds
_CHECK_AND_INCREMENT_LUA = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local limit = tonumber(ARGV[1])
local amount = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])

if limit == -1 then
    redis.call('INCRBY', KEYS[1], amount)
    redis.call('EXPIRE', KEYS[1], ttl)
    return 1
end

if current + amount <= limit then
    redis.call('INCRBY', KEYS[1], amount)
    redis.call('EXPIRE', KEYS[1], ttl)
    return 1
else
    return 0
end
"""

# Module-level singleton instance (lazy initialization)
_shared_instance: "UsageLimiter | None" = None


def get_usage_limiter(redis_url: str) -> "UsageLimiter":
    """Get the shared UsageLimiter singleton instance.

    Reuses a single Redis connection pool across the application.
    """
    global _shared_instance
    if _shared_instance is None:
        _shared_instance = UsageLimiter(redis_url=redis_url)
    return _shared_instance


class UsageLimiter:
    """Redis-based usage limiter for tenant resource consumption."""

    def __init__(self, redis_url: str) -> None:
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._lua_script: str | None = None

    def _current_period_key(self) -> str:
        """Get the YYYY-MM key for the current billing period."""
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m")

    def _usage_key(self, tenant_id: str, resource_type: str) -> str:
        """Build the Redis key for usage tracking."""
        period = self._current_period_key()
        return f"usage:{tenant_id}:{period}:{resource_type}"

    def _limits_cache_key(self, tenant_id: str) -> str:
        """Build the Redis key for cached plan limits."""
        return f"limits:{tenant_id}"

    async def check_and_increment(
        self, tenant_id: str, resource_type: str, amount: int = 1
    ) -> bool:
        """Atomically check usage against plan limit and increment if allowed.

        Returns True if the usage was allowed, False if limit would be exceeded.
        Uses a Lua script for atomic check-and-increment.
        """
        limits = await self._get_tenant_limits(tenant_id)
        limit_key = f"{resource_type}_limit"
        limit_value = limits.get(limit_key, 0)

        key = self._usage_key(tenant_id, resource_type)
        # TTL: keep keys for 35 days (covers the full month plus buffer)
        ttl = 35 * 24 * 3600

        result = await self._redis.eval(
            _CHECK_AND_INCREMENT_LUA,
            1,
            key,
            str(limit_value),
            str(amount),
            str(ttl),
        )
        return result == 1

    async def get_usage(self, tenant_id: str) -> dict[str, dict[str, int]]:
        """Get current usage and limits for a tenant.

        Returns a dict with keys: leads, emails, linkedin, campaigns.
        Each value has 'current' and 'limit' fields.
        """
        limits = await self._get_tenant_limits(tenant_id)
        resource_types = ["leads", "emails", "linkedin", "campaigns"]
        result: dict[str, dict[str, int]] = {}

        for rt in resource_types:
            key = self._usage_key(tenant_id, rt)
            current = await self._redis.get(key)
            result[rt] = {
                "current": int(current) if current else 0,
                "limit": limits.get(f"{rt}_limit", 0),
            }

        return result

    async def reset_monthly_usage(self, tenant_id: str) -> None:
        """Delete Redis keys for the current billing period."""
        period = self._current_period_key()
        resource_types = ["leads", "emails", "linkedin", "campaigns"]

        for rt in resource_types:
            key = f"usage:{tenant_id}:{period}:{rt}"
            await self._redis.delete(key)

    async def _get_tenant_limits(self, tenant_id: str) -> dict[str, int]:
        """Query plan limits for a tenant, with 5-minute Redis cache.

        Returns a dict like:
        {
            "leads_limit": 500,
            "emails_limit": 1000,
            "linkedin_limit": 0,
            "campaigns_limit": 1,
        }
        """
        cache_key = self._limits_cache_key(tenant_id)
        cached = await self._redis.get(cache_key)

        if cached:
            return json.loads(cached)

        # Default limits if no subscription found (free tier / fallback)
        default_limits = {
            "leads_limit": 0,
            "emails_limit": 0,
            "linkedin_limit": 0,
            "campaigns_limit": 0,
        }

        # In production, this would query the database for the tenant's
        # active subscription and associated plan limits.
        # For now, we check if limits were previously set via set_tenant_limits.
        limits_data_key = f"tenant_plan:{tenant_id}"
        stored = await self._redis.get(limits_data_key)

        if stored:
            limits = json.loads(stored)
        else:
            limits = default_limits

        # Cache for 5 minutes
        await self._redis.setex(cache_key, 300, json.dumps(limits))
        return limits

    async def set_tenant_limits(self, tenant_id: str, limits: dict[str, int]) -> None:
        """Store tenant plan limits in Redis (called when subscription changes).

        Args:
            limits: Dict with keys like leads_limit, emails_limit, linkedin_limit, campaigns_limit
        """
        limits_data_key = f"tenant_plan:{tenant_id}"
        await self._redis.set(limits_data_key, json.dumps(limits))

        # Invalidate the cache
        cache_key = self._limits_cache_key(tenant_id)
        await self._redis.delete(cache_key)

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()
