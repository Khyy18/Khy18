"""Simple in-memory per-tenant rate limiter."""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from fastapi import Depends, HTTPException, status

from ai_office.api.dependencies import get_current_user_optional
from ai_office.core.models import User

# In-memory store: tenant_id -> list of request timestamps
_rate_store: Dict[str, List[float]] = {}

# Rate limits per plan (requests per minute)
RATE_LIMITS: Dict[str, int] = {
    "trial": 60,
    "starter": 60,
    "pro": 200,
    "agency": 500,
}

WINDOW_SECONDS = 60


def _cleanup_old_timestamps(timestamps: List[float], now: float) -> List[float]:
    """Remove timestamps older than the rate limit window."""
    cutoff = now - WINDOW_SECONDS
    return [t for t in timestamps if t > cutoff]


async def check_rate_limit(
    user: Optional[User] = Depends(get_current_user_optional),
) -> None:
    """FastAPI dependency that enforces per-tenant rate limiting.

    If no user is authenticated, rate limiting is skipped.
    """
    if user is None:
        return

    tenant = user.tenant
    if tenant is None:
        return

    tenant_id = tenant.id
    plan_name = tenant.plan_name or "trial"
    limit = RATE_LIMITS.get(plan_name, RATE_LIMITS["trial"])

    now = time.time()

    # Get or create timestamp list for this tenant
    if tenant_id not in _rate_store:
        _rate_store[tenant_id] = []

    # Clean up old timestamps
    _rate_store[tenant_id] = _cleanup_old_timestamps(_rate_store[tenant_id], now)

    # Check if over limit
    if len(_rate_store[tenant_id]) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
        )

    # Record this request
    _rate_store[tenant_id].append(now)
