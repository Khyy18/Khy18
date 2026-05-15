"""Per-tenant LLM spending control with Redis-based tracking."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class LLMBudgetManager:
    """Per-tenant LLM spending control with Redis-based tracking."""

    # Cost per 1K tokens by model (in cents)
    MODEL_COSTS: dict[str, dict[str, float]] = {
        "gpt-4": {"input": 3.0, "output": 6.0},
        "gpt-4-turbo": {"input": 1.0, "output": 3.0},
        "gpt-3.5-turbo": {"input": 0.05, "output": 0.15},
        "claude-3-sonnet-20240229": {"input": 0.3, "output": 1.5},
        "claude-3-opus-20240229": {"input": 1.5, "output": 7.5},
        "llama3-8b-8192": {"input": 0.05, "output": 0.05},
    }

    # Monthly budget limits per plan (in cents)
    PLAN_BUDGETS: dict[str, int] = {
        "starter": 1000,       # $10
        "growth": 5000,        # $50
        "scale": 20000,        # $200
        "enterprise": 50000,   # $500
    }

    def __init__(self, redis_url: str) -> None:
        """Initialize the budget manager with a Redis connection.

        Args:
            redis_url: Redis connection URL.
        """
        self._redis: aioredis.Redis = aioredis.from_url(
            redis_url, decode_responses=True
        )

    def _current_period(self) -> str:
        """Get the current billing period key (YYYY-MM)."""
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _budget_key(self, tenant_id: str, period: str, metric: str) -> str:
        """Build the Redis key for budget tracking.

        Args:
            tenant_id: The tenant identifier.
            period: The billing period (YYYY-MM).
            metric: One of input_tokens, output_tokens, cost_cents.
        """
        return f"llm_budget:{tenant_id}:{period}:{metric}"

    def estimate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> float:
        """Calculate cost in cents for a given token usage.

        Args:
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
            model: The model name.

        Returns:
            Cost in cents.
        """
        costs = self.MODEL_COSTS.get(model, {"input": 0.05, "output": 0.15})
        input_cost = (input_tokens / 1000.0) * costs["input"]
        output_cost = (output_tokens / 1000.0) * costs["output"]
        return input_cost + output_cost

    async def record_usage(
        self,
        tenant_id: str,
        input_tokens: int,
        output_tokens: int,
        model: str,
    ) -> dict[str, Any]:
        """Record LLM token usage for a tenant.

        Calculates cost and increments Redis counters atomically.

        Args:
            tenant_id: The tenant identifier.
            input_tokens: Number of input tokens used.
            output_tokens: Number of output tokens used.
            model: The model name used for cost calculation.

        Returns:
            Usage summary dict with tokens, cost, and period.
        """
        period = self._current_period()
        cost_cents = self.estimate_cost(input_tokens, output_tokens, model)
        # Round cost to integer cents for Redis INCRBY
        cost_int = int(round(cost_cents))

        input_key = self._budget_key(tenant_id, period, "input_tokens")
        output_key = self._budget_key(tenant_id, period, "output_tokens")
        cost_key = self._budget_key(tenant_id, period, "cost_cents")

        # TTL: 35 days to cover the billing period plus buffer
        ttl = 35 * 24 * 3600

        # Increment input tokens
        await self._redis.incrby(input_key, input_tokens)
        await self._redis.expire(input_key, ttl)

        # Increment output tokens
        await self._redis.incrby(output_key, output_tokens)
        await self._redis.expire(output_key, ttl)

        # Increment cost
        await self._redis.incrby(cost_key, cost_int)
        await self._redis.expire(cost_key, ttl)

        return {
            "tenant_id": tenant_id,
            "period": period,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model": model,
            "cost_cents": cost_cents,
            "recorded": True,
        }

    async def check_budget(
        self, tenant_id: str, plan: str = "starter"
    ) -> dict[str, Any]:
        """Check current budget status for a tenant.

        Args:
            tenant_id: The tenant identifier.
            plan: The plan name for budget limit lookup.

        Returns:
            Dict with allowed, status, usage_cents, budget_cents, usage_pct.
        """
        period = self._current_period()
        cost_key = self._budget_key(tenant_id, period, "cost_cents")

        current_raw = await self._redis.get(cost_key)
        usage_cents = int(current_raw) if current_raw else 0
        budget_cents = self.PLAN_BUDGETS.get(plan, self.PLAN_BUDGETS["starter"])

        if budget_cents == 0:
            usage_pct = 100.0
        else:
            usage_pct = (usage_cents / budget_cents) * 100.0

        if usage_cents >= budget_cents:
            status = "exceeded"
            allowed = False
        elif usage_pct >= 80.0:
            status = "near_limit"
            allowed = True
        else:
            status = "ok"
            allowed = True

        return {
            "allowed": allowed,
            "status": status,
            "usage_cents": usage_cents,
            "budget_cents": budget_cents,
            "usage_pct": round(usage_pct, 2),
        }

    async def get_usage_summary(
        self, tenant_id: str, plan: str = "starter"
    ) -> dict[str, Any]:
        """Get detailed usage summary for a tenant.

        Args:
            tenant_id: The tenant identifier.
            plan: The plan name for budget limit lookup.

        Returns:
            Dict with current spend, limit, percentage, and token counts.
        """
        period = self._current_period()
        input_key = self._budget_key(tenant_id, period, "input_tokens")
        output_key = self._budget_key(tenant_id, period, "output_tokens")
        cost_key = self._budget_key(tenant_id, period, "cost_cents")

        input_raw = await self._redis.get(input_key)
        output_raw = await self._redis.get(output_key)
        cost_raw = await self._redis.get(cost_key)

        input_tokens = int(input_raw) if input_raw else 0
        output_tokens = int(output_raw) if output_raw else 0
        usage_cents = int(cost_raw) if cost_raw else 0
        budget_cents = self.PLAN_BUDGETS.get(plan, self.PLAN_BUDGETS["starter"])

        if budget_cents == 0:
            usage_pct = 100.0
        else:
            usage_pct = (usage_cents / budget_cents) * 100.0

        return {
            "tenant_id": tenant_id,
            "period": period,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "usage_cents": usage_cents,
            "budget_cents": budget_cents,
            "usage_pct": round(usage_pct, 2),
            "plan": plan,
        }

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()
