"""Tests for the UsageLimiter."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from compliance.usage_limiter import UsageLimiter


@pytest.fixture
def usage_limiter(mock_redis):
    """Create a UsageLimiter with mocked Redis."""
    limiter = UsageLimiter.__new__(UsageLimiter)
    limiter._redis = mock_redis
    limiter._lua_script = None
    return limiter


async def test_check_and_increment_allows_when_under_limit(usage_limiter, mock_redis):
    """Test check_and_increment allows when usage is under limit."""
    # Set up limits in Redis
    tenant_id = "tenant-123"
    limits = {"leads_limit": 100, "emails_limit": 500, "linkedin_limit": 50, "campaigns_limit": 5}
    mock_redis._store[f"tenant_plan:{tenant_id}"] = json.dumps(limits)

    result = await usage_limiter.check_and_increment(tenant_id, "emails", 1)

    assert result is True
    mock_redis.eval.assert_called_once()


async def test_check_and_increment_rejects_when_at_limit(usage_limiter, mock_redis):
    """Test check_and_increment rejects when at limit."""
    tenant_id = "tenant-456"
    limits = {"leads_limit": 5, "emails_limit": 10, "linkedin_limit": 0, "campaigns_limit": 1}
    mock_redis._store[f"tenant_plan:{tenant_id}"] = json.dumps(limits)

    # Simulate being at limit by setting up the eval to return 0
    original_eval = mock_redis.eval.side_effect

    async def eval_at_limit(script, num_keys, *args):
        key = args[0]
        limit_val = int(args[1])
        amount = int(args[2])
        # Pre-fill usage to be at limit
        mock_redis._store[key] = str(limit_val)
        current = int(mock_redis._store.get(key, "0"))
        if limit_val == -1 or current + amount <= limit_val:
            mock_redis._store[key] = str(current + amount)
            return 1
        return 0

    mock_redis.eval = AsyncMock(side_effect=eval_at_limit)

    result = await usage_limiter.check_and_increment(tenant_id, "emails", 1)

    assert result is False


async def test_get_usage_returns_correct_values(usage_limiter, mock_redis):
    """Test get_usage returns correct current/limit values."""
    tenant_id = "tenant-789"
    limits = {"leads_limit": 500, "emails_limit": 1000, "linkedin_limit": 100, "campaigns_limit": 5}
    mock_redis._store[f"tenant_plan:{tenant_id}"] = json.dumps(limits)

    # Set some current usage
    period_key = usage_limiter._current_period_key()
    mock_redis._store[f"usage:{tenant_id}:{period_key}:leads"] = "42"
    mock_redis._store[f"usage:{tenant_id}:{period_key}:emails"] = "150"

    result = await usage_limiter.get_usage(tenant_id)

    assert result["leads"]["current"] == 42
    assert result["leads"]["limit"] == 500
    assert result["emails"]["current"] == 150
    assert result["emails"]["limit"] == 1000
    assert result["linkedin"]["current"] == 0
    assert result["linkedin"]["limit"] == 100
    assert result["campaigns"]["current"] == 0
    assert result["campaigns"]["limit"] == 5


async def test_reset_monthly_usage_clears_keys(usage_limiter, mock_redis):
    """Test monthly reset clears Redis usage keys."""
    tenant_id = "tenant-reset"
    period_key = usage_limiter._current_period_key()

    # Set some usage
    mock_redis._store[f"usage:{tenant_id}:{period_key}:leads"] = "100"
    mock_redis._store[f"usage:{tenant_id}:{period_key}:emails"] = "200"
    mock_redis._store[f"usage:{tenant_id}:{period_key}:linkedin"] = "30"
    mock_redis._store[f"usage:{tenant_id}:{period_key}:campaigns"] = "2"

    await usage_limiter.reset_monthly_usage(tenant_id)

    # Verify delete was called for each resource type
    assert mock_redis.delete.call_count == 4


async def test_check_and_increment_unlimited_when_negative_one(usage_limiter, mock_redis):
    """Test check_and_increment allows unlimited usage when limit is -1."""
    tenant_id = "tenant-unlimited"
    limits = {"leads_limit": -1, "emails_limit": -1, "linkedin_limit": -1, "campaigns_limit": -1}
    mock_redis._store[f"tenant_plan:{tenant_id}"] = json.dumps(limits)

    result = await usage_limiter.check_and_increment(tenant_id, "emails", 1)
    assert result is True
