"""Tests for per-tenant rate limiting."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
import pytest_asyncio

from ai_office.api.rate_limit import (
    RATE_LIMITS,
    _cleanup_old_timestamps,
    _rate_store,
    check_rate_limit,
)
from ai_office.api.auth import create_access_token, hash_password
from ai_office.core.models import Tenant, User


@pytest_asyncio.fixture
async def rate_limit_tenant(async_session):
    """Create a tenant for rate limit tests."""
    tenant = Tenant(
        name="Rate Test Co",
        email="rate@test.com",
        plan_name="trial",
    )
    async_session.add(tenant)
    await async_session.commit()
    await async_session.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def rate_limit_user(async_session, rate_limit_tenant):
    """Create a user for rate limit tests."""
    user = User(
        tenant_id=rate_limit_tenant.id,
        email="rateuser@test.com",
        password_hash=hash_password("ratepass"),
        role="member",
        is_super_admin=False,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture(autouse=True)
def clear_rate_store():
    """Clear rate store before each test."""
    _rate_store.clear()
    yield
    _rate_store.clear()


@pytest.mark.asyncio
async def test_rate_limiter_allows_under_limit(rate_limit_user):
    """Rate limiter allows requests under the limit."""
    # Trial plan allows 60 requests per minute
    # Calling check_rate_limit should not raise
    for _ in range(5):
        await check_rate_limit(user=rate_limit_user)
    # If no exception raised, test passes


@pytest.mark.asyncio
async def test_rate_limiter_blocks_over_limit(rate_limit_user, rate_limit_tenant):
    """Rate limiter returns 429 when over limit."""
    from fastapi import HTTPException

    tenant_id = rate_limit_tenant.id
    limit = RATE_LIMITS["trial"]  # 60

    # Pre-fill the rate store to simulate being at the limit
    now = time.time()
    _rate_store[tenant_id] = [now - i * 0.5 for i in range(limit)]

    # Next request should be blocked
    with pytest.raises(HTTPException) as exc_info:
        await check_rate_limit(user=rate_limit_user)

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_rate_limiter_skips_unauthenticated():
    """Rate limiter skips when no user is authenticated."""
    # Should not raise any exception
    await check_rate_limit(user=None)


@pytest.mark.asyncio
async def test_rate_limiter_cleans_old_timestamps(rate_limit_user, rate_limit_tenant):
    """Old timestamps are cleaned up during rate limit check."""
    tenant_id = rate_limit_tenant.id

    # Add timestamps that are older than 60 seconds
    old_time = time.time() - 120
    _rate_store[tenant_id] = [old_time + i for i in range(50)]

    # The request should succeed since old timestamps get cleaned
    await check_rate_limit(user=rate_limit_user)

    # Only the new timestamp should remain
    assert len(_rate_store[tenant_id]) == 1


def test_cleanup_old_timestamps():
    """Test the cleanup helper function directly."""
    now = time.time()
    timestamps = [
        now - 120,  # too old
        now - 90,   # too old
        now - 30,   # recent
        now - 10,   # recent
        now,        # current
    ]
    cleaned = _cleanup_old_timestamps(timestamps, now)
    assert len(cleaned) == 3


@pytest.mark.asyncio
async def test_rate_limits_per_plan(async_session):
    """Different plans have different rate limits."""
    assert RATE_LIMITS["trial"] == 60
    assert RATE_LIMITS["starter"] == 60
    assert RATE_LIMITS["pro"] == 200
    assert RATE_LIMITS["agency"] == 500
