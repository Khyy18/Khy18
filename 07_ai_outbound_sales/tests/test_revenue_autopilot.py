"""Tests for the Revenue Autopilot system."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import MagicMock

from core.models import (
    Campaign,
    CampaignStatus,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
    ChannelType,
    MessageDirection,
    Plan,
    PlanName,
    Subscription,
    SubscriptionStatus,
    Tenant,
)
from scheduler.revenue_autopilot import RevenueAutopilot
from tests.conftest import (
    make_campaign,
    make_lead,
    make_message,
    make_plan,
    make_subscription,
    make_tenant,
)


@pytest.fixture
def autopilot_settings():
    """Create mock settings for revenue autopilot."""
    s = MagicMock()
    s.redis_url = "redis://localhost:6379/0"
    return s


@pytest.fixture
def autopilot(session_factory, autopilot_settings):
    """Create a RevenueAutopilot instance for testing."""
    return RevenueAutopilot(
        session_factory=session_factory,
        settings=autopilot_settings,
    )


async def test_track_mrr_with_active_subscriptions(autopilot, async_session):
    """track_mrr should sum price_cents of active subscriptions."""
    # Create plan and tenant
    plan = make_plan(price_cents=9900, name=PlanName.growth)
    tenant = make_tenant()

    async_session.add(plan)
    async_session.add(tenant)
    await async_session.flush()

    # Create active subscription
    sub = make_subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status=SubscriptionStatus.active,
    )
    async_session.add(sub)
    await async_session.commit()

    result = await autopilot.track_mrr(async_session)
    assert result["mrr_cents"] == 9900
    assert result["active_subscriptions"] == 1


async def test_track_mrr_empty(autopilot, async_session):
    """track_mrr should return zeros when no active subscriptions exist."""
    result = await autopilot.track_mrr(async_session)
    assert result["mrr_cents"] == 0
    assert result["active_subscriptions"] == 0


async def test_check_inactive_clients_detects_inactive(autopilot, async_session, caplog):
    """check_inactive_clients should warn about tenants with no recent messages."""
    import logging

    tenant = make_tenant(name="Inactive Corp")
    async_session.add(tenant)
    await async_session.commit()

    with caplog.at_level(logging.WARNING):
        await autopilot.check_inactive_clients(async_session)

    assert "Inactive Corp" in caplog.text
    assert "no messages" in caplog.text.lower() or "Engagement" in caplog.text


async def test_check_subscription_expiry_detects_expiring(autopilot, async_session, caplog):
    """check_subscription_expiry should warn about subscriptions expiring within 7 days."""
    import logging

    plan = make_plan(price_cents=2900, name=PlanName.starter)
    tenant = make_tenant()

    async_session.add(plan)
    async_session.add(tenant)
    await async_session.flush()

    # Create subscription expiring in 3 days
    sub = make_subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status=SubscriptionStatus.active,
    )
    sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=3)
    sub.current_period_start = datetime.now(timezone.utc) - timedelta(days=27)
    async_session.add(sub)
    await async_session.commit()

    with caplog.at_level(logging.WARNING):
        await autopilot.check_subscription_expiry(async_session)

    assert "Renewal reminder" in caplog.text or "expires" in caplog.text
