"""Voice AI usage tracking service.

Manages call usage counting, overage detection, and addon validation
for the Voice AI add-on billing system.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import VoiceAddon, VoiceAddonPlan

logger = logging.getLogger(__name__)

# Voice add-on plan configuration
VOICE_PLANS: dict[str, dict[str, Any]] = {
    "voice_starter": {
        "display_name": "Voice Starter",
        "price_cents": 2900,
        "calls_included": 50,
        "overage_rate_cents": 50,
        "stripe_price_id": "price_voice_starter",
    },
    "voice_pro": {
        "display_name": "Voice Pro",
        "price_cents": 7900,
        "calls_included": 200,
        "overage_rate_cents": 50,
        "stripe_price_id": "price_voice_pro",
    },
    "voice_scale": {
        "display_name": "Voice Scale",
        "price_cents": 19900,
        "calls_included": 600,
        "overage_rate_cents": 50,
        "stripe_price_id": "price_voice_scale",
    },
}


class VoiceUsageError(Exception):
    """Raised when voice usage check fails."""

    pass


class NoActiveVoiceAddonError(VoiceUsageError):
    """Raised when no active voice addon exists for a tenant."""

    pass


async def get_active_voice_addon(
    session: AsyncSession, tenant_id: uuid.UUID | str
) -> VoiceAddon | None:
    """Get the active voice addon for a tenant."""
    tid = uuid.UUID(str(tenant_id)) if not isinstance(tenant_id, uuid.UUID) else tenant_id
    result = await session.execute(
        select(VoiceAddon)
        .where(VoiceAddon.tenant_id == tid)
        .where(VoiceAddon.is_active == True)  # noqa: E712
        .order_by(VoiceAddon.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def check_and_increment_usage(
    session: AsyncSession, tenant_id: uuid.UUID | str
) -> dict[str, Any]:
    """Check if tenant can make a call and increment usage.

    Returns dict with call permission info. Always allows the call if addon
    is active (overage is tracked but not blocked).

    Raises NoActiveVoiceAddonError if no active addon exists.
    """
    addon = await get_active_voice_addon(session, tenant_id)
    if addon is None:
        raise NoActiveVoiceAddonError(
            "No active Voice AI add-on. Subscribe to a voice plan to make calls."
        )

    # Increment usage
    addon.calls_used_this_period += 1
    is_overage = addon.calls_used_this_period > addon.calls_limit

    await session.flush()

    return {
        "allowed": True,
        "calls_used": addon.calls_used_this_period,
        "calls_limit": addon.calls_limit,
        "is_overage": is_overage,
        "overage_calls": max(0, addon.calls_used_this_period - addon.calls_limit),
        "overage_cost_cents": (
            max(0, addon.calls_used_this_period - addon.calls_limit)
            * addon.overage_rate_cents
        ),
    }


async def get_voice_usage(
    session: AsyncSession, tenant_id: uuid.UUID | str
) -> dict[str, Any]:
    """Get current voice usage for a tenant."""
    addon = await get_active_voice_addon(session, tenant_id)
    if addon is None:
        return {
            "plan_name": None,
            "is_active": False,
            "calls_used": 0,
            "calls_limit": 0,
            "calls_remaining": 0,
            "overage_calls": 0,
            "overage_cost_cents": 0,
            "overage_rate_cents": 50,
            "period_start": None,
            "period_end": None,
        }

    overage_calls = max(0, addon.calls_used_this_period - addon.calls_limit)
    calls_remaining = max(0, addon.calls_limit - addon.calls_used_this_period)

    return {
        "plan_name": addon.plan_name.value if addon.plan_name else None,
        "is_active": addon.is_active,
        "calls_used": addon.calls_used_this_period,
        "calls_limit": addon.calls_limit,
        "calls_remaining": calls_remaining,
        "overage_calls": overage_calls,
        "overage_cost_cents": overage_calls * addon.overage_rate_cents,
        "overage_rate_cents": addon.overage_rate_cents,
        "period_start": (
            addon.period_start.isoformat() if addon.period_start else None
        ),
        "period_end": addon.period_end.isoformat() if addon.period_end else None,
    }


async def reset_period_usage(
    session: AsyncSession, tenant_id: uuid.UUID | str, period_start: datetime, period_end: datetime
) -> None:
    """Reset usage for a new billing period."""
    addon = await get_active_voice_addon(session, tenant_id)
    if addon is None:
        return

    addon.calls_used_this_period = 0
    addon.period_start = period_start
    addon.period_end = period_end
    await session.flush()
