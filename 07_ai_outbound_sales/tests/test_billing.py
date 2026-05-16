"""Tests for the billing webhook handler."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from core.models import (
    Plan,
    PlanName,
    Subscription,
    SubscriptionStatus,
    Tenant,
)
from dashboard.routes.billing import _handle_webhook_event
from tests.conftest import make_plan, make_subscription, make_tenant


async def test_webhook_invoice_paid_sets_active(async_session):
    """Test webhook handler processes invoice.paid (sets status=active)."""
    tenant = make_tenant()
    async_session.add(tenant)
    plan = make_plan()
    async_session.add(plan)
    await async_session.flush()

    sub = make_subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        stripe_subscription_id="sub_paid_123",
        status=SubscriptionStatus.past_due,
    )
    async_session.add(sub)
    await async_session.flush()

    data_object = {"subscription": "sub_paid_123"}
    await _handle_webhook_event(async_session, "invoice.paid", data_object)

    result = await async_session.execute(
        select(Subscription).where(Subscription.id == sub.id)
    )
    updated_sub = result.scalar_one()
    assert updated_sub.status == SubscriptionStatus.active


async def test_webhook_payment_failed_sets_past_due(async_session):
    """Test webhook handler processes invoice.payment_failed (sets status=past_due)."""
    tenant = make_tenant()
    async_session.add(tenant)
    plan = make_plan()
    async_session.add(plan)
    await async_session.flush()

    sub = make_subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        stripe_subscription_id="sub_fail_456",
        status=SubscriptionStatus.active,
    )
    async_session.add(sub)
    await async_session.flush()

    data_object = {"subscription": "sub_fail_456"}
    await _handle_webhook_event(async_session, "invoice.payment_failed", data_object)

    result = await async_session.execute(
        select(Subscription).where(Subscription.id == sub.id)
    )
    updated_sub = result.scalar_one()
    assert updated_sub.status == SubscriptionStatus.past_due


async def test_webhook_subscription_deleted_sets_canceled(async_session):
    """Test webhook handler processes customer.subscription.deleted (sets status=canceled)."""
    tenant = make_tenant()
    async_session.add(tenant)
    plan = make_plan()
    async_session.add(plan)
    await async_session.flush()

    sub = make_subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        stripe_subscription_id="sub_del_789",
        status=SubscriptionStatus.active,
    )
    async_session.add(sub)
    await async_session.flush()

    data_object = {"id": "sub_del_789"}
    await _handle_webhook_event(async_session, "customer.subscription.deleted", data_object)

    result = await async_session.execute(
        select(Subscription).where(Subscription.id == sub.id)
    )
    updated_sub = result.scalar_one()
    assert updated_sub.status == SubscriptionStatus.canceled


async def test_webhook_idempotency_no_subscription(async_session):
    """Test webhook does nothing when subscription ID not found (idempotent)."""
    data_object = {"subscription": "sub_nonexistent_000"}
    # Should not raise
    await _handle_webhook_event(async_session, "invoice.paid", data_object)


async def test_webhook_unhandled_event_type(async_session):
    """Test unhandled event type does not raise."""
    data_object = {"id": "some_object_id"}
    # Should not raise for unknown event types
    await _handle_webhook_event(async_session, "charge.succeeded", data_object)


# ---------- Tests for domains_limit and plan tiers ----------


async def test_plan_has_domains_limit(async_session):
    """Test that Plan model correctly stores domains_limit."""
    plan = make_plan(domains_limit=3)
    async_session.add(plan)
    await async_session.flush()

    result = await async_session.execute(select(Plan).where(Plan.id == plan.id))
    stored_plan = result.scalar_one()
    assert stored_plan.domains_limit == 3


async def test_plan_domains_limit_default(async_session):
    """Test that make_plan factory defaults domains_limit to 1."""
    plan = make_plan()
    async_session.add(plan)
    await async_session.flush()

    result = await async_session.execute(select(Plan).where(Plan.id == plan.id))
    stored_plan = result.scalar_one()
    assert stored_plan.domains_limit == 1


async def test_plan_name_agency_enum(async_session):
    """Test that PlanName enum includes 'agency' instead of 'scale'."""
    assert hasattr(PlanName, "agency")
    assert not hasattr(PlanName, "scale")

    plan = make_plan(name=PlanName.agency, domains_limit=-1)
    async_session.add(plan)
    await async_session.flush()

    result = await async_session.execute(select(Plan).where(Plan.id == plan.id))
    stored_plan = result.scalar_one()
    assert stored_plan.name == PlanName.agency


async def test_plan_response_includes_domains_limit(async_session):
    """Test that PlanResponse schema includes domains_limit field."""
    from dashboard.schemas import PlanResponse

    plan = make_plan(domains_limit=5)
    async_session.add(plan)
    await async_session.flush()

    response = PlanResponse.model_validate(plan)
    assert response.domains_limit == 5


async def test_checkout_endpoint_exists():
    """Test that POST /api/billing/checkout endpoint is registered."""
    from dashboard.routes.billing import router

    checkout_routes = [
        r for r in router.routes
        if hasattr(r, "path") and r.path == "/api/billing/checkout" and "POST" in r.methods
    ]
    assert len(checkout_routes) == 1
