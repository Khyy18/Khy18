"""Billing API routes - plan management, subscription, usage, and Stripe webhook."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.config import settings
from core.models import Plan, Subscription, SubscriptionStatus, User
from dashboard.auth import get_current_user
from dashboard.schemas import (
    ChangePlanRequest,
    CheckoutSessionResponse,
    InvoiceResponse,
    PlanResponse,
    SubscribeRequest,
    SubscriptionResponse,
    UsageResponse,
)
from integrations.billing import StripeClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])

# Redis key prefix for storing processed Stripe event IDs (idempotency)
_WEBHOOK_EVENT_TTL = 60 * 60 * 24 * 3  # 3 days


async def _get_session():
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


def _get_stripe_client() -> StripeClient:
    return StripeClient(secret_key=settings.stripe_secret_key)


async def _propagate_plan_limits(tenant_id: str, plan: Plan) -> None:
    """Propagate plan limits to Redis after a plan change."""
    from compliance.usage_limiter import get_usage_limiter

    limiter = get_usage_limiter(settings.redis_url)
    limits = {
        "leads_limit": plan.leads_limit,
        "emails_limit": plan.emails_limit,
        "linkedin_limit": plan.linkedin_limit,
        "campaigns_limit": plan.campaigns_limit,
    }
    await limiter.set_tenant_limits(tenant_id, limits)


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> list[Plan]:
    """List all available plans."""
    result = await session.execute(select(Plan).order_by(Plan.price_cents.asc()))
    return list(result.scalars().all())


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> Subscription:
    """Get current tenant subscription with plan details."""
    result = await session.execute(
        select(Subscription)
        .options(selectinload(Subscription.plan))
        .where(Subscription.tenant_id == current_user.tenant_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found",
        )
    return subscription


@router.post("/subscribe", response_model=CheckoutSessionResponse)
async def subscribe(
    data: SubscribeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Create a Stripe Checkout Session for subscribing to a plan."""
    # Get the plan
    plan_result = await session.execute(select(Plan).where(Plan.id == data.plan_id))
    plan = plan_result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found"
        )

    # Get existing subscription to find stripe_customer_id
    sub_result = await session.execute(
        select(Subscription)
        .where(Subscription.tenant_id == current_user.tenant_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    subscription = sub_result.scalar_one_or_none()

    # Fix #6: If no stripe_customer_id, attempt to create one on the fly
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No subscription record found. Please contact support.",
        )

    if not subscription.stripe_customer_id:
        stripe_client = _get_stripe_client()
        customer = await stripe_client.create_customer(
            email=current_user.email,
            name=current_user.email,
            metadata={"tenant_id": str(current_user.tenant_id)},
        )
        if "error" in customer:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to create Stripe customer. Please try again later.",
            )
        subscription.stripe_customer_id = customer.get("id")
        await session.flush()

    stripe_client = _get_stripe_client()
    checkout = await stripe_client.create_checkout_session(
        customer_id=subscription.stripe_customer_id,
        price_id=plan.stripe_price_id or "",
        success_url=data.success_url,
        cancel_url=data.cancel_url,
    )

    if "error" in checkout:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create checkout session",
        )

    return {"checkout_url": checkout.get("url", "")}


@router.post("/checkout", response_model=CheckoutSessionResponse)
async def checkout(
    data: SubscribeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Create a Stripe Checkout Session (alias for /subscribe)."""
    return await subscribe(data=data, current_user=current_user, session=session)


@router.post("/change-plan", response_model=SubscriptionResponse)
async def change_plan(
    data: ChangePlanRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> Subscription:
    """Upgrade or downgrade subscription plan."""
    # Get current subscription
    sub_result = await session.execute(
        select(Subscription)
        .options(selectinload(Subscription.plan))
        .where(Subscription.tenant_id == current_user.tenant_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    subscription = sub_result.scalar_one_or_none()
    if subscription is None or not subscription.stripe_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription to change",
        )

    # Get target plan
    plan_result = await session.execute(select(Plan).where(Plan.id == data.plan_id))
    new_plan = plan_result.scalar_one_or_none()
    if new_plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found"
        )

    stripe_client = _get_stripe_client()
    result = await stripe_client.change_subscription_plan(
        subscription_id=subscription.stripe_subscription_id,
        new_price_id=new_plan.stripe_price_id or "",
    )

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to change plan",
        )

    # Update local subscription
    subscription.plan_id = new_plan.id
    await session.flush()
    await session.refresh(subscription)

    # Fix #4: Propagate new plan limits to Redis
    await _propagate_plan_limits(str(current_user.tenant_id), new_plan)

    return subscription


@router.post("/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> Subscription:
    """Cancel the current subscription."""
    sub_result = await session.execute(
        select(Subscription)
        .options(selectinload(Subscription.plan))
        .where(Subscription.tenant_id == current_user.tenant_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    subscription = sub_result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found",
        )

    if subscription.stripe_subscription_id:
        stripe_client = _get_stripe_client()
        result = await stripe_client.cancel_subscription(
            subscription_id=subscription.stripe_subscription_id
        )
        if "error" in result:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to cancel subscription",
            )

    subscription.status = SubscriptionStatus.canceled
    await session.flush()
    await session.refresh(subscription)
    return subscription


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get current usage for the tenant."""
    from compliance.usage_limiter import get_usage_limiter

    limiter = get_usage_limiter(settings.redis_url)
    usage = await limiter.get_usage(str(current_user.tenant_id))
    return {
        "leads_used": usage["leads"]["current"],
        "leads_limit": usage["leads"]["limit"],
        "emails_used": usage["emails"]["current"],
        "emails_limit": usage["emails"]["limit"],
        "linkedin_used": usage["linkedin"]["current"],
        "linkedin_limit": usage["linkedin"]["limit"],
        "campaigns_active": usage["campaigns"]["current"],
        "campaigns_limit": usage["campaigns"]["limit"],
        "period_start": datetime.now(timezone.utc).strftime("%Y-%m-01"),
    }


@router.get("/invoices", response_model=list[InvoiceResponse])
async def get_invoices(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> list[dict]:
    """Get invoice history for the tenant."""
    sub_result = await session.execute(
        select(Subscription)
        .where(Subscription.tenant_id == current_user.tenant_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    subscription = sub_result.scalar_one_or_none()
    if subscription is None or not subscription.stripe_customer_id:
        return []

    stripe_client = _get_stripe_client()
    raw_invoices = await stripe_client.get_invoices(
        customer_id=subscription.stripe_customer_id
    )

    invoices = []
    for inv in raw_invoices:
        created_ts = inv.get("created", 0)
        invoices.append({
            "id": inv.get("id", ""),
            "amount_due": inv.get("amount_due", 0),
            "status": inv.get("status", "unknown"),
            "created": datetime.fromtimestamp(created_ts, tz=timezone.utc),
            "hosted_invoice_url": inv.get("hosted_invoice_url"),
        })

    return invoices


# ---------- Stripe Webhook (no auth required) ----------


@router.post("/webhook")
async def stripe_webhook(request: Request) -> dict:
    """Handle Stripe webhook events. No auth - verified via Stripe signature.

    Uses Redis-based event ID deduplication to ensure idempotency under retries.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    stripe_client = _get_stripe_client()
    event = await stripe_client.construct_webhook_event(
        payload=payload,
        sig_header=sig_header,
        webhook_secret=settings.stripe_webhook_secret,
    )

    if "error" in event:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook signature verification failed",
        )

    # Fix #1: Idempotency - check if we already processed this event
    event_id = event.get("id", "")
    if event_id:
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            dedup_key = f"stripe_event:{event_id}"
            already_processed = await redis_client.set(
                dedup_key, "1", nx=True, ex=_WEBHOOK_EVENT_TTL
            )
            if not already_processed:
                # Event was already processed (key already existed)
                logger.info("Skipping duplicate Stripe event: %s", event_id)
                return {"status": "ok", "duplicate": True}
        finally:
            await redis_client.close()

    event_type = event.get("type", "")
    data_object = event.get("data", {}).get("object", {})

    from core.db import get_session as _gs

    async for session in _gs():
        await _handle_webhook_event(session, event_type, data_object)
        break

    return {"status": "ok"}


async def _handle_webhook_event(
    session: AsyncSession, event_type: str, data_object: dict
) -> None:
    """Process a verified Stripe webhook event."""
    if event_type == "invoice.paid":
        stripe_sub_id = data_object.get("subscription")
        if stripe_sub_id:
            result = await session.execute(
                select(Subscription).where(
                    Subscription.stripe_subscription_id == stripe_sub_id
                )
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.status = SubscriptionStatus.active
                await session.commit()

    elif event_type == "invoice.payment_failed":
        stripe_sub_id = data_object.get("subscription")
        if stripe_sub_id:
            result = await session.execute(
                select(Subscription).where(
                    Subscription.stripe_subscription_id == stripe_sub_id
                )
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.status = SubscriptionStatus.past_due
                await session.commit()

    elif event_type == "customer.subscription.deleted":
        stripe_sub_id = data_object.get("id")
        if stripe_sub_id:
            result = await session.execute(
                select(Subscription).where(
                    Subscription.stripe_subscription_id == stripe_sub_id
                )
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.status = SubscriptionStatus.canceled
                await session.commit()

    elif event_type == "customer.subscription.updated":
        stripe_sub_id = data_object.get("id")
        if stripe_sub_id:
            result = await session.execute(
                select(Subscription)
                .options(selectinload(Subscription.plan))
                .where(
                    Subscription.stripe_subscription_id == stripe_sub_id
                )
            )
            sub = result.scalar_one_or_none()
            if sub:
                # Update period dates
                period_start = data_object.get("current_period_start")
                period_end = data_object.get("current_period_end")
                if period_start:
                    sub.current_period_start = datetime.fromtimestamp(
                        period_start, tz=timezone.utc
                    )
                if period_end:
                    sub.current_period_end = datetime.fromtimestamp(
                        period_end, tz=timezone.utc
                    )

                # Update plan if price changed
                new_plan: Plan | None = None
                items = data_object.get("items", {}).get("data", [])
                if items:
                    new_price_id = items[0].get("price", {}).get("id")
                    if new_price_id:
                        plan_result = await session.execute(
                            select(Plan).where(Plan.stripe_price_id == new_price_id)
                        )
                        new_plan = plan_result.scalar_one_or_none()
                        if new_plan:
                            sub.plan_id = new_plan.id

                await session.commit()

                # Fix #4: Propagate new limits to Redis after subscription update
                resolved_plan = new_plan if new_plan else sub.plan
                if resolved_plan and sub.tenant_id:
                    await _propagate_plan_limits(str(sub.tenant_id), resolved_plan)
    else:
        logger.debug("Unhandled webhook event type: %s", event_type)
