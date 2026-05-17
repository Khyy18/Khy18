"""Tests for the LLMBudgetManager per-tenant spending control."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from compliance.llm_budget import LLMBudgetManager


@pytest.fixture
def budget_manager(mock_redis: AsyncMock) -> LLMBudgetManager:
    """Create an LLMBudgetManager with mocked Redis."""
    manager = LLMBudgetManager.__new__(LLMBudgetManager)
    manager._redis = mock_redis
    return manager


# --- Cost Estimation Tests ---


class TestEstimateCost:
    """Tests for token cost calculation."""

    def test_estimate_cost_gpt4(self, budget_manager: LLMBudgetManager) -> None:
        """GPT-4 cost calculation: 1K input tokens + 1K output = 9 cents."""
        cost = budget_manager.estimate_cost(1000, 1000, "gpt-4")
        # input: 1000/1000 * 3.0 = 3.0 cents
        # output: 1000/1000 * 6.0 = 6.0 cents
        assert cost == pytest.approx(9.0)

    def test_estimate_cost_gpt4_turbo(self, budget_manager: LLMBudgetManager) -> None:
        """GPT-4-turbo cost calculation."""
        cost = budget_manager.estimate_cost(1000, 1000, "gpt-4-turbo")
        # input: 1.0 + output: 3.0 = 4.0 cents
        assert cost == pytest.approx(4.0)

    def test_estimate_cost_gpt35(self, budget_manager: LLMBudgetManager) -> None:
        """GPT-3.5-turbo cost calculation."""
        cost = budget_manager.estimate_cost(1000, 1000, "gpt-3.5-turbo")
        # input: 0.05 + output: 0.15 = 0.2 cents
        assert cost == pytest.approx(0.2)

    def test_estimate_cost_groq(self, budget_manager: LLMBudgetManager) -> None:
        """Groq/Llama cost calculation (very cheap)."""
        cost = budget_manager.estimate_cost(1000, 1000, "llama3-8b-8192")
        # input: 0.05 + output: 0.05 = 0.1 cents
        assert cost == pytest.approx(0.1)

    def test_estimate_cost_claude_sonnet(
        self, budget_manager: LLMBudgetManager
    ) -> None:
        """Claude Sonnet cost calculation."""
        cost = budget_manager.estimate_cost(1000, 1000, "claude-3-sonnet-20240229")
        # input: 0.3 + output: 1.5 = 1.8 cents
        assert cost == pytest.approx(1.8)

    def test_estimate_cost_claude_opus(
        self, budget_manager: LLMBudgetManager
    ) -> None:
        """Claude Opus cost calculation."""
        cost = budget_manager.estimate_cost(1000, 1000, "claude-3-opus-20240229")
        # input: 1.5 + output: 7.5 = 9.0 cents
        assert cost == pytest.approx(9.0)

    def test_estimate_cost_unknown_model_uses_defaults(
        self, budget_manager: LLMBudgetManager
    ) -> None:
        """Unknown model uses default costs (same as gpt-3.5-turbo)."""
        cost = budget_manager.estimate_cost(1000, 1000, "unknown-model-v1")
        # Default: input: 0.05 + output: 0.15 = 0.2 cents
        assert cost == pytest.approx(0.2)

    def test_estimate_cost_scales_with_tokens(
        self, budget_manager: LLMBudgetManager
    ) -> None:
        """Cost scales linearly with token count."""
        cost_1k = budget_manager.estimate_cost(1000, 1000, "gpt-4")
        cost_2k = budget_manager.estimate_cost(2000, 2000, "gpt-4")
        assert cost_2k == pytest.approx(cost_1k * 2)


# --- Plan Budgets Tests ---


class TestPlanBudgets:
    """Tests for plan budget configuration."""

    def test_plan_budgets_starter(self, budget_manager: LLMBudgetManager) -> None:
        """Starter plan has $10 (1000 cents) budget."""
        assert budget_manager.PLAN_BUDGETS["starter"] == 1000

    def test_plan_budgets_growth(self, budget_manager: LLMBudgetManager) -> None:
        """Growth plan has $50 (5000 cents) budget."""
        assert budget_manager.PLAN_BUDGETS["growth"] == 5000

    def test_plan_budgets_scale(self, budget_manager: LLMBudgetManager) -> None:
        """Scale plan has $200 (20000 cents) budget."""
        assert budget_manager.PLAN_BUDGETS["scale"] == 20000

    def test_plan_budgets_enterprise(self, budget_manager: LLMBudgetManager) -> None:
        """Enterprise plan has $500 (50000 cents) budget."""
        assert budget_manager.PLAN_BUDGETS["enterprise"] == 50000


# --- Record Usage Tests ---


class TestRecordUsage:
    """Tests for usage recording with Redis operations."""

    @pytest.mark.asyncio
    async def test_record_usage_increments_counters(
        self, budget_manager: LLMBudgetManager, mock_redis: AsyncMock
    ) -> None:
        """Recording usage calls Redis INCRBY with correct values."""
        mock_redis.incrby = AsyncMock(return_value=100)
        mock_redis.expire = AsyncMock(return_value=True)

        result = await budget_manager.record_usage(
            tenant_id="tenant-1",
            input_tokens=500,
            output_tokens=200,
            model="gpt-4",
        )

        assert result["tenant_id"] == "tenant-1"
        assert result["input_tokens"] == 500
        assert result["output_tokens"] == 200
        assert result["model"] == "gpt-4"
        assert result["recorded"] is True
        assert result["cost_cents"] > 0

        # Verify Redis incrby was called (at least for tokens and cost)
        assert mock_redis.incrby.call_count >= 3

    @pytest.mark.asyncio
    async def test_record_usage_cost_calculation(
        self, budget_manager: LLMBudgetManager, mock_redis: AsyncMock
    ) -> None:
        """Recorded cost matches estimate_cost calculation."""
        mock_redis.incrby = AsyncMock(return_value=100)
        mock_redis.expire = AsyncMock(return_value=True)

        result = await budget_manager.record_usage(
            tenant_id="tenant-1",
            input_tokens=1000,
            output_tokens=1000,
            model="gpt-4",
        )

        expected_cost = budget_manager.estimate_cost(1000, 1000, "gpt-4")
        assert result["cost_cents"] == pytest.approx(expected_cost)


# --- Budget Check Tests ---


class TestCheckBudget:
    """Tests for budget checking at various usage levels."""

    @pytest.mark.asyncio
    async def test_check_budget_under_limit(
        self, budget_manager: LLMBudgetManager, mock_redis: AsyncMock
    ) -> None:
        """Under 80% usage returns status='ok' and allowed=True."""
        # Starter plan = 1000 cents. Set usage to 500 (50%)
        mock_redis.get = AsyncMock(return_value="500")

        result = await budget_manager.check_budget("tenant-1", "starter")

        assert result["allowed"] is True
        assert result["status"] == "ok"
        assert result["usage_cents"] == 500
        assert result["budget_cents"] == 1000
        assert result["usage_pct"] == 50.0

    @pytest.mark.asyncio
    async def test_check_budget_near_limit(
        self, budget_manager: LLMBudgetManager, mock_redis: AsyncMock
    ) -> None:
        """At 80%+ usage returns status='near_limit' and allowed=True."""
        # Starter plan = 1000 cents. Set usage to 850 (85%)
        mock_redis.get = AsyncMock(return_value="850")

        result = await budget_manager.check_budget("tenant-1", "starter")

        assert result["allowed"] is True
        assert result["status"] == "near_limit"
        assert result["usage_cents"] == 850
        assert result["usage_pct"] == 85.0

    @pytest.mark.asyncio
    async def test_check_budget_exceeded(
        self, budget_manager: LLMBudgetManager, mock_redis: AsyncMock
    ) -> None:
        """At 100%+ usage returns status='exceeded' and allowed=False."""
        # Starter plan = 1000 cents. Set usage to 1100 (110%)
        mock_redis.get = AsyncMock(return_value="1100")

        result = await budget_manager.check_budget("tenant-1", "starter")

        assert result["allowed"] is False
        assert result["status"] == "exceeded"
        assert result["usage_cents"] == 1100
        assert result["usage_pct"] == 110.0

    @pytest.mark.asyncio
    async def test_check_budget_exactly_at_limit(
        self, budget_manager: LLMBudgetManager, mock_redis: AsyncMock
    ) -> None:
        """At exactly 100% usage returns status='exceeded' and allowed=False."""
        mock_redis.get = AsyncMock(return_value="1000")

        result = await budget_manager.check_budget("tenant-1", "starter")

        assert result["allowed"] is False
        assert result["status"] == "exceeded"

    @pytest.mark.asyncio
    async def test_check_budget_zero_usage(
        self, budget_manager: LLMBudgetManager, mock_redis: AsyncMock
    ) -> None:
        """Zero usage returns status='ok' and allowed=True."""
        mock_redis.get = AsyncMock(return_value=None)

        result = await budget_manager.check_budget("tenant-1", "growth")

        assert result["allowed"] is True
        assert result["status"] == "ok"
        assert result["usage_cents"] == 0
        assert result["budget_cents"] == 5000
        assert result["usage_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_check_budget_growth_plan(
        self, budget_manager: LLMBudgetManager, mock_redis: AsyncMock
    ) -> None:
        """Growth plan uses 5000 cents budget."""
        mock_redis.get = AsyncMock(return_value="4500")

        result = await budget_manager.check_budget("tenant-1", "growth")

        assert result["budget_cents"] == 5000
        assert result["status"] == "near_limit"
        assert result["allowed"] is True


# --- Usage Summary Tests ---


class TestGetUsageSummary:
    """Tests for usage summary retrieval."""

    @pytest.mark.asyncio
    async def test_get_usage_summary(
        self, budget_manager: LLMBudgetManager, mock_redis: AsyncMock
    ) -> None:
        """Usage summary returns all token and cost information."""
        call_count = 0
        values = ["5000", "2000", "300"]

        async def mock_get_seq(key):
            nonlocal call_count
            if call_count < len(values):
                val = values[call_count]
                call_count += 1
                return val
            return None

        mock_redis.get = AsyncMock(side_effect=mock_get_seq)

        result = await budget_manager.get_usage_summary("tenant-1", "starter")

        assert result["tenant_id"] == "tenant-1"
        assert result["input_tokens"] == 5000
        assert result["output_tokens"] == 2000
        assert result["usage_cents"] == 300
        assert result["budget_cents"] == 1000
        assert result["plan"] == "starter"
        assert "period" in result
        assert "usage_pct" in result
