"""Tests for AiRateLimiter from arbitrage.ai_rate_limiter."""

from __future__ import annotations

import asyncio

import pytest

from arbitrage.ai_rate_limiter import AiRateLimiter


@pytest.mark.asyncio
async def test_acquire_succeeds() -> None:
    """First acquire returns True."""
    limiter = AiRateLimiter(rpm=10, burst=5)
    result = await limiter.acquire(priority="NORMAL", timeout=5.0)
    assert result is True


@pytest.mark.asyncio
async def test_acquire_respects_limit() -> None:
    """After RPM acquires, next one times out."""
    limiter = AiRateLimiter(rpm=2, burst=1)
    # Exhaust all tokens
    assert await limiter.acquire(priority="NORMAL", timeout=1.0) is True
    assert await limiter.acquire(priority="NORMAL", timeout=1.0) is True
    # Third should timeout (only 2 RPM)
    result = await limiter.acquire(priority="NORMAL", timeout=0.2)
    assert result is False


@pytest.mark.asyncio
async def test_get_stats_structure() -> None:
    """Returns dict with expected keys."""
    limiter = AiRateLimiter(rpm=10)
    await limiter.acquire(priority="NORMAL", timeout=1.0)
    stats = limiter.get_stats()
    assert "rpm_limit" in stats
    assert "used_tokens" in stats
    assert "available_tokens" in stats
    assert "queue_lengths" in stats
    assert "total_acquired" in stats
    assert "total_rejected" in stats
    assert stats["rpm_limit"] == 10
    assert stats["total_acquired"] == 1


@pytest.mark.asyncio
async def test_priority_ordering() -> None:
    """CRITICAL gets served before LOW when tokens are scarce."""
    limiter = AiRateLimiter(rpm=3, burst=1)
    # Use up 2 tokens
    await limiter.acquire(priority="LOW", timeout=1.0)
    await limiter.acquire(priority="LOW", timeout=1.0)

    # Now only 1 token left. CRITICAL should get it.
    result = await limiter.acquire(priority="CRITICAL", timeout=1.0)
    assert result is True

    # LOW should be blocked now
    result = await limiter.acquire(priority="LOW", timeout=0.2)
    assert result is False
