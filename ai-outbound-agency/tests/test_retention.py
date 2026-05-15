"""Tests for scheduler/retention.py - Retention engine checks."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    Campaign,
    CampaignStatus,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
    Plan,
    PlanName,
    Subscription,
    SubscriptionStatus,
    Tenant,
    UsageRecord,
)
from scheduler.retention import RetentionEngine
from tests.conftest import (
    make_campaign,
    make_lead,
    make_message,
    make_plan,
    make_subscription,
    make_tenant,
)


@pytest.fixture
def retention_engine(session_factory, mock_settings):
    """Create a RetentionEngine instance for testing."""
    return RetentionEngine(session_factory=session_factory, settings=mock_settings)


# ---------- Milestone Tests ----------


@pytest.mark.asyncio
async def test_milestone_detection_first_meeting(async_session: AsyncSession, retention_engine):
    """1 booked lead should trigger milestone 1."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    lead = make_lead(tenant_id=tenant.id, status=LeadStatus.booked)
    async_session.add(lead)
    await async_session.flush()

    with patch("scheduler.retention._send_to_channels", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        with patch("scheduler.retention._get_tenant_notification_config", new_callable=AsyncMock) as mock_config:
            mock_config.return_value = ([], {})
            result = await retention_engine.check_milestones(tenant.id, async_session)

    assert result == 1


@pytest.mark.asyncio
async def test_milestone_detection_ten_meetings(async_session: AsyncSession, retention_engine):
    """10 booked leads should trigger milestone 10."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    for _ in range(10):
        lead = make_lead(tenant_id=tenant.id, status=LeadStatus.booked)
        async_session.add(lead)
    await async_session.flush()

    with patch("scheduler.retention._send_to_channels", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        with patch("scheduler.retention._get_tenant_notification_config", new_callable=AsyncMock) as mock_config:
            mock_config.return_value = ([], {})
            result = await retention_engine.check_milestones(tenant.id, async_session)

    assert result == 10


@pytest.mark.asyncio
async def test_no_milestone_at_3_meetings(async_session: AsyncSession, retention_engine):
    """3 booked leads should return the highest reached milestone (1)."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    for _ in range(3):
        lead = make_lead(tenant_id=tenant.id, status=LeadStatus.booked)
        async_session.add(lead)
    await async_session.flush()

    with patch("scheduler.retention._send_to_channels", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        with patch("scheduler.retention._get_tenant_notification_config", new_callable=AsyncMock) as mock_config:
            mock_config.return_value = ([], {})
            result = await retention_engine.check_milestones(tenant.id, async_session)

    assert result == 1


@pytest.mark.asyncio
async def test_milestone_skip_eleven_meetings(async_session: AsyncSession, retention_engine):
    """11 booked leads (skipping exact 10) should still detect milestone 10."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    for _ in range(11):
        lead = make_lead(tenant_id=tenant.id, status=LeadStatus.booked)
        async_session.add(lead)
    await async_session.flush()

    with patch("scheduler.retention._send_to_channels", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        with patch("scheduler.retention._get_tenant_notification_config", new_callable=AsyncMock) as mock_config:
            mock_config.return_value = ([], {})
            result = await retention_engine.check_milestones(tenant.id, async_session)

    assert result == 10


@pytest.mark.asyncio
async def test_no_milestone_at_zero_meetings(async_session: AsyncSession, retention_engine):
    """0 booked leads should not trigger any milestone."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    with patch("scheduler.retention._send_to_channels", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        with patch("scheduler.retention._get_tenant_notification_config", new_callable=AsyncMock) as mock_config:
            mock_config.return_value = ([], {})
            result = await retention_engine.check_milestones(tenant.id, async_session)

    assert result is None


# ---------- Engagement Tests ----------


@pytest.mark.asyncio
async def test_engagement_check_inactive(async_session: AsyncSession, retention_engine):
    """No messages in 7 days should return inactive status."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    campaign = make_campaign(tenant_id=tenant.id, status=CampaignStatus.active)
    async_session.add(campaign)
    await async_session.flush()

    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)
    await async_session.flush()

    # Add a message from 10 days ago (older than 7 days)
    old_message = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        status=MessageStatus.sent,
        sent_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    async_session.add(old_message)
    await async_session.flush()

    result = await retention_engine.check_engagement(tenant.id, async_session)
    assert result["status"] == "inactive"
    assert "suggestion" in result


@pytest.mark.asyncio
async def test_engagement_check_active(async_session: AsyncSession, retention_engine):
    """Messages within 7 days should return active status."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    campaign = make_campaign(tenant_id=tenant.id, status=CampaignStatus.active)
    async_session.add(campaign)
    await async_session.flush()

    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)
    await async_session.flush()

    # Add a recent message
    recent_message = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        status=MessageStatus.sent,
        sent_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    async_session.add(recent_message)
    await async_session.flush()

    result = await retention_engine.check_engagement(tenant.id, async_session)
    assert result["status"] == "active"
    assert result["messages_sent_7d"] >= 1


# ---------- Upsell Tests ----------


@pytest.mark.asyncio
async def test_upsell_trigger_at_80_percent(async_session: AsyncSession, retention_engine):
    """Usage at 80% of plan limit should trigger upsell recommendation."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    plan = make_plan(
        leads_limit=100,
        emails_limit=1000,
        linkedin_limit=50,
    )
    async_session.add(plan)
    await async_session.flush()

    subscription = make_subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status=SubscriptionStatus.active,
    )
    async_session.add(subscription)
    await async_session.flush()

    # Create usage record at 80% of leads limit
    usage = UsageRecord(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        period_start=datetime.now(timezone.utc) - timedelta(days=1),
        leads_used=80,  # 80% of 100
        emails_used=100,  # 10% of 1000
        linkedin_used=5,  # 10% of 50
    )
    async_session.add(usage)
    await async_session.flush()

    result = await retention_engine.check_upsell_triggers(tenant.id, async_session)
    assert result is not None
    assert result["recommendation"] == "upsell"
    assert len(result["triggers"]) >= 1
    assert result["triggers"][0]["metric"] == "leads"
    assert result["triggers"][0]["percent"] >= 80.0


# ---------- Lead Pool Tests ----------


@pytest.mark.asyncio
async def test_lead_pool_depletion(async_session: AsyncSession, retention_engine):
    """Fewer than 10 new leads should return a depletion warning."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    # Add only 5 new leads
    for _ in range(5):
        lead = make_lead(tenant_id=tenant.id, status=LeadStatus.new)
        async_session.add(lead)
    await async_session.flush()

    result = await retention_engine.check_lead_pool(tenant.id, async_session)
    assert result is not None
    assert result["warning"] == "lead_pool_depleting"
    assert result["new_leads_remaining"] == 5


@pytest.mark.asyncio
async def test_lead_pool_sufficient(async_session: AsyncSession, retention_engine):
    """10 or more new leads should not trigger warning."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    # Add 15 new leads
    for _ in range(15):
        lead = make_lead(tenant_id=tenant.id, status=LeadStatus.new)
        async_session.add(lead)
    await async_session.flush()

    result = await retention_engine.check_lead_pool(tenant.id, async_session)
    assert result is None
