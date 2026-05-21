"""Tests for BounceMonitor - record_bounce, should_pause at threshold, record_send."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def bounce_monitor(mock_redis):
    """Create a BounceMonitor with a mocked Redis client."""
    with patch("channels.email.bounce_monitor.aioredis.from_url", return_value=mock_redis):
        from channels.email.bounce_monitor import BounceMonitor
        monitor = BounceMonitor(redis_url="redis://localhost:6379/0")
    return monitor


@pytest.mark.asyncio
async def test_record_bounce_increments_counters(bounce_monitor, mock_redis):
    """Test that record_bounce calls Redis pipeline to increment bounce counters."""
    # The pipeline mock tracks calls
    pipe = mock_redis.pipeline()

    await bounce_monitor.record_bounce("example.com", "hard")

    # Pipeline should have been called with incr and expire
    assert pipe.incr.called
    assert pipe.expire.called
    pipe.execute.assert_awaited()


@pytest.mark.asyncio
async def test_record_send_increments_send_counter(bounce_monitor, mock_redis):
    """Test that record_send increments the sends counter without resetting consecutive bounces."""
    pipe = mock_redis.pipeline()

    await bounce_monitor.record_send("example.com")

    assert pipe.incr.called
    pipe.execute.assert_awaited()

    # record_send should NOT reset consecutive_hard counter
    # (the old bug was that it did)
    mock_redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_pause_high_bounce_rate(bounce_monitor, mock_redis):
    """Test should_pause_domain returns True when bounce rate > 5% with 20+ sends."""
    from datetime import date

    today = date.today().isoformat()
    domain = "bad-domain.com"

    # Simulate 25 sends and 2 bounces (8% bounce rate)
    mock_redis._store[f"sends:{domain}:{today}"] = "25"
    mock_redis._store[f"bounces:{domain}:{today}"] = "2"
    mock_redis._store[f"consecutive_hard:{domain}"] = "0"

    result = await bounce_monitor.should_pause_domain(domain)
    assert result is True


@pytest.mark.asyncio
async def test_should_pause_consecutive_hard_bounces(bounce_monitor, mock_redis):
    """Test should_pause_domain returns True when consecutive hard bounces > 3."""
    from datetime import date

    today = date.today().isoformat()
    domain = "failing-domain.com"

    # Few sends, low bounce rate, but 4 consecutive hard bounces
    mock_redis._store[f"sends:{domain}:{today}"] = "5"
    mock_redis._store[f"bounces:{domain}:{today}"] = "0"
    mock_redis._store[f"consecutive_hard:{domain}"] = "4"

    result = await bounce_monitor.should_pause_domain(domain)
    assert result is True


@pytest.mark.asyncio
async def test_should_not_pause_under_threshold(bounce_monitor, mock_redis):
    """Test should_pause_domain returns False when under all thresholds."""
    from datetime import date

    today = date.today().isoformat()
    domain = "good-domain.com"

    # 30 sends, 1 bounce (3.3% - under 5%), 1 consecutive hard
    mock_redis._store[f"sends:{domain}:{today}"] = "30"
    mock_redis._store[f"bounces:{domain}:{today}"] = "1"
    mock_redis._store[f"consecutive_hard:{domain}"] = "1"

    result = await bounce_monitor.should_pause_domain(domain)
    assert result is False


@pytest.mark.asyncio
async def test_is_domain_paused(bounce_monitor, mock_redis):
    """Test is_domain_paused returns correct state."""
    domain = "paused-domain.com"

    # Not paused initially
    result = await bounce_monitor.is_domain_paused(domain)
    assert result is False

    # Set paused
    mock_redis._store[f"paused:{domain}"] = "1"
    result = await bounce_monitor.is_domain_paused(domain)
    assert result is True


@pytest.mark.asyncio
async def test_get_bounce_rate_zero_sends(bounce_monitor, mock_redis):
    """Test get_bounce_rate returns 0.0 when there are no sends."""
    result = await bounce_monitor.get_bounce_rate("no-sends.com")
    assert result == 0.0


@pytest.mark.asyncio
async def test_get_bounce_rate_calculation(bounce_monitor, mock_redis):
    """Test get_bounce_rate calculates correctly."""
    from datetime import date

    today = date.today().isoformat()
    domain = "test.com"

    mock_redis._store[f"sends:{domain}:{today}"] = "100"
    mock_redis._store[f"bounces:{domain}:{today}"] = "5"

    result = await bounce_monitor.get_bounce_rate(domain)
    assert result == 0.05
