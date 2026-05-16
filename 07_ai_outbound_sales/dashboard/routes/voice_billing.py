"""Voice AI add-on billing routes.

Provides endpoints for managing Voice AI add-on subscriptions,
viewing available plans, checking usage, and cancellation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.models import Subscription, User, VoiceAddon, VoiceAddonPlan
from dashboard.auth import get_current_user
from dashboard.schemas import (
    VoiceAddonCancelResponse,
    VoiceAddonCheckoutRequest,
    VoiceAddonCheckoutResponse,
    VoicePlanResponse,
    VoiceUsageResponse,
)
from integrations.billing import StripeClient
from integrations.voice_usage import VOICE_PLANS, get_active_voice_addon, get_voice_usage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["voice-billing"])


async def _get_session():
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


def _get_stripe_client() -> StripeClient:
    return StripeClient(secret_key=settings.stripe_secret_key)


@router.get("/voice-plans", response_model=list[VoicePlanResponse])
async def list_voice_plans(
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List available Voice AI add-on plans with pricing."""
    plans = []
    for plan_name, config in VOICE_PLANS.items():
        plans.append({
            "plan_name": plan_name,
            "display_name": config["display_name"],
            "price_cents": config["price_cents"],
            "calls_included": config["calls_included"],
            "overage_rate_cents": config["overage_rate_cents"],
            "stripe_price_id": config["stripe_price_id"],
        })
    return plans


@router.post("/voice-addon/checkout", response_model=VoiceAddonCheckoutResponse)
async def voice_addon_checkout(
    data: VoiceAddonCheckoutRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Create a Stripe Checkout Session for a Voice AI add-on subscription."""
    # Validate plan name
    if data.plan_name not in VOICE_PLANS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid voice plan: {data.plan_name}. "
            f"Available plans: {', '.join(VOICE_PLANS.keys())}",
        )

    # Check if tenant already has an active voice addon
    existing = await get_active_voice_addon(session, current_user.tenant_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tenant already has an active Voice AI add-on. "
            "Cancel the existing one before subscribing to a new plan.",
        )

    # Get existing subscription to find stripe_customer_id
    sub_result = await session.execute(
        select(Subscription)
        .where(Subscription.tenant_id == current_user.tenant_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    subscription = sub_result.scalar_one_or_none()

    if subscription is None or not subscription.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No billing subscription found. Please set up your main subscription first.",
        )

    plan_config = VOICE_PLANS[data.plan_name]
    stripe_client = _get_stripe_client()

    checkout = await stripe_client.create_checkout_session(
        customer_id=subscription.stripe_customer_id,
        price_id=plan_config["stripe_price_id"],
        success_url=data.success_url,
        cancel_url=data.cancel_url,
    )

    if "error" in checkout:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create checkout session",
        )

    # Create the voice addon record (will be activated via webhook on payment)
    now = datetime.now(timezone.utc)
    addon = VoiceAddon(
        tenant_id=current_user.tenant_id,
        plan_name=VoiceAddonPlan(data.plan_name),
        calls_limit=plan_config["calls_included"],
        overage_rate_cents=plan_config["overage_rate_cents"],
        period_start=now,
        period_end=None,
        is_active=True,
    )
    session.add(addon)
    await session.flush()

    return {"checkout_url": checkout.get("url", "")}


@router.get("/voice-usage", response_model=VoiceUsageResponse)
async def voice_usage(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get current Voice AI usage for the billing period."""
    usage = await get_voice_usage(session, current_user.tenant_id)
    return usage


@router.post("/voice-addon/cancel", response_model=VoiceAddonCancelResponse)
async def cancel_voice_addon(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Cancel the active Voice AI add-on subscription."""
    addon = await get_active_voice_addon(session, current_user.tenant_id)
    if addon is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Voice AI add-on found",
        )

    # Cancel in Stripe if subscription ID exists
    if addon.stripe_subscription_id:
        stripe_client = _get_stripe_client()
        result = await stripe_client.cancel_subscription(
            subscription_id=addon.stripe_subscription_id
        )
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to cancel voice add-on in Stripe",
            )

    addon.is_active = False
    await session.flush()

    return {
        "status": "canceled",
        "message": "Voice AI add-on has been canceled. "
        "Remaining calls in the current period are still available.",
    }
