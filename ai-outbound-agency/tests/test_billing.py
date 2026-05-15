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
