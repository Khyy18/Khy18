"""Billing endpoints for plan management, Stripe checkout, and usage tracking."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.auth import get_current_user
from ai_office.core.billing import PLANS, get_billing_period_start, get_tenant_plan
from ai_office.core.config import settings
from ai_office.core.database import get_session
from ai_office.core.models import Task, Tenant, TenantAgent, User

router = APIRouter(prefix="/api/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    """Request body for creating a Stripe checkout session."""

    plan_name: str


class CheckoutResponse(BaseModel):
    """Response with Stripe checkout URL."""

    checkout_url: str


class SubscriptionResponse(BaseModel):
    """Response with current subscription info."""

    plan_name: str
    stripe_subscription_id: str | None = None
    is_active: bool


class UsageResponse(BaseModel):
    """Response with current usage stats."""

    tasks_this_period: int
    max_tasks_per_month: int
    active_agents: int
    max_agents: int


class PlanInfo(BaseModel):
    """Plan information for public listing."""

    key: str
    name: str
    price: int
    max_agents: int
    max_tasks_per_month: int
    features: List[str]


@router.get("/plans", response_model=List[PlanInfo])
async def list_plans() -> List[PlanInfo]:
    """Return all available plans. Publicly accessible."""
    return [
        PlanInfo(
            key=key,
            name=plan["name"],
            price=plan["price"],
            max_agents=plan["max_agents"],
            max_tasks_per_month=plan["max_tasks_per_month"],
            features=plan["features"],
        )
        for key, plan in PLANS.items()
    ]


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CheckoutResponse:
    """Create a Stripe checkout session for the requested plan."""
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=503,
            detail="Stripe is not configured. Please contact support.",
        )

    # Validate plan
    if body.plan_name not in PLANS or body.plan_name == "trial":
        raise HTTPException(status_code=400, detail="Invalid plan name")

    # Map plan to Stripe price ID
    price_map: Dict[str, str] = {
        "starter": settings.stripe_price_starter,
        "pro": settings.stripe_price_pro,
        "agency": settings.stripe_price_agency,
    }
    price_id = price_map.get(body.plan_name)
    if not price_id:
        raise HTTPException(status_code=400, detail="Price not configured for this plan")

    try:
        import stripe

        stripe.api_key = settings.stripe_secret_key

        # Get tenant email
        tenant_result = await session.execute(
            select(Tenant).where(Tenant.id == current_user.tenant_id)
        )
        tenant = tenant_result.scalar_one_or_none()
        customer_email = tenant.email if tenant else current_user.email

        checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=customer_email,
            metadata={
                "tenant_id": current_user.tenant_id,
                "plan_name": body.plan_name,
            },
            success_url="https://app.example.com/billing?success=true",
            cancel_url="https://app.example.com/billing?canceled=true",
        )

        return CheckoutResponse(checkout_url=checkout_session.url)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Stripe error: {str(e)}")


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SubscriptionResponse:
    """Get current tenant subscription status."""
    tenant_result = await session.execute(
        select(Tenant).where(Tenant.id == current_user.tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return SubscriptionResponse(
        plan_name=tenant.plan_name,
        stripe_subscription_id=tenant.stripe_subscription_id,
        is_active=tenant.is_active,
    )


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UsageResponse:
    """Get current usage stats for the tenant."""
    tenant_id = current_user.tenant_id

    # Get tenant plan
    tenant_result = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    plan = get_tenant_plan(tenant)

    # Count tasks in current billing period
    period_start = get_billing_period_start()
    task_count_result = await session.execute(
        select(func.count(Task.id)).where(
            Task.tenant_id == tenant_id,
            Task.created_at >= period_start,
        )
    )
    tasks_this_period = task_count_result.scalar() or 0

    # Count active agents
    agent_count_result = await session.execute(
        select(func.count(TenantAgent.id)).where(
            TenantAgent.tenant_id == tenant_id,
            TenantAgent.is_enabled == True,  # noqa: E712
        )
    )
    active_agents = agent_count_result.scalar() or 0

    return UsageResponse(
        tasks_this_period=tasks_this_period,
        max_tasks_per_month=plan["max_tasks_per_month"],
        active_agents=active_agents,
        max_agents=plan["max_agents"],
    )


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """Handle Stripe webhook events. Uses raw body for signature verification."""
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook secret not configured")

    try:
        import stripe

        stripe.api_key = settings.stripe_secret_key

        # Get raw body for signature verification
        body = await request.body()
        sig_header = request.headers.get("stripe-signature", "")

        event = stripe.Webhook.construct_event(
            body, sig_header, settings.stripe_webhook_secret
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {str(e)}")

    # Process event
    event_type = event.get("type", "") if isinstance(event, dict) else event.type

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(event, session)
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(event, session)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(event, session)

    return {"status": "ok"}


async def _handle_checkout_completed(event: Any, session: AsyncSession) -> None:
    """Handle checkout.session.completed event."""
    data = event.get("data", {}) if isinstance(event, dict) else event.data
    obj = data.get("object", {}) if isinstance(data, dict) else data.object

    metadata = obj.get("metadata", {}) if isinstance(obj, dict) else getattr(obj, "metadata", {})
    tenant_id = metadata.get("tenant_id") if isinstance(metadata, dict) else getattr(metadata, "tenant_id", None)
    plan_name = metadata.get("plan_name") if isinstance(metadata, dict) else getattr(metadata, "plan_name", None)

    customer_id = obj.get("customer") if isinstance(obj, dict) else getattr(obj, "customer", None)
    subscription_id = obj.get("subscription") if isinstance(obj, dict) else getattr(obj, "subscription", None)

    if tenant_id and plan_name:
        result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if tenant:
            tenant.plan_name = plan_name
            if customer_id:
                tenant.stripe_customer_id = customer_id
            if subscription_id:
                tenant.stripe_subscription_id = subscription_id
            await session.commit()


async def _handle_subscription_updated(event: Any, session: AsyncSession) -> None:
    """Handle customer.subscription.updated event."""
    data = event.get("data", {}) if isinstance(event, dict) else event.data
    obj = data.get("object", {}) if isinstance(data, dict) else data.object

    subscription_id = obj.get("id") if isinstance(obj, dict) else getattr(obj, "id", None)

    if subscription_id:
        result = await session.execute(
            select(Tenant).where(Tenant.stripe_subscription_id == subscription_id)
        )
        tenant = result.scalar_one_or_none()
        if tenant:
            # Update plan from subscription metadata or items
            metadata = obj.get("metadata", {}) if isinstance(obj, dict) else getattr(obj, "metadata", {})
            new_plan = metadata.get("plan_name") if isinstance(metadata, dict) else getattr(metadata, "plan_name", None)
            if new_plan and new_plan in PLANS:
                tenant.plan_name = new_plan
                await session.commit()


async def _handle_subscription_deleted(event: Any, session: AsyncSession) -> None:
    """Handle customer.subscription.deleted event."""
    data = event.get("data", {}) if isinstance(event, dict) else event.data
    obj = data.get("object", {}) if isinstance(data, dict) else data.object

    subscription_id = obj.get("id") if isinstance(obj, dict) else getattr(obj, "id", None)

    if subscription_id:
        result = await session.execute(
            select(Tenant).where(Tenant.stripe_subscription_id == subscription_id)
        )
        tenant = result.scalar_one_or_none()
        if tenant:
            tenant.plan_name = "trial"
            tenant.stripe_subscription_id = None
            await session.commit()
