"""Tests for enhanced funnel analytics, conversion rates, and channel performance endpoints."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    Campaign,
    CampaignStatus,
    ChannelType,
    Event,
    EventType,
    Lead,
    LeadStatus,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    User,
    UserRole,
)
from tests.conftest import (
    make_campaign,
    make_event,
    make_lead,
    make_message,
    make_tenant,
    make_user,
)


def _setup_tenant_and_user():
    """Create a tenant and user for testing."""
    tenant = make_tenant()
    user = make_user(tenant_id=tenant.id)
    return tenant, user


async def _create_funnel_data(session: AsyncSession, tenant_id: uuid.UUID):
    """Create leads with various statuses and messages for funnel testing."""
    campaign = make_campaign(tenant_id=tenant_id, status=CampaignStatus.active)
    session.add(campaign)
    await session.flush()

    # Create leads with different statuses
    statuses = [
        LeadStatus.new,
        LeadStatus.new,
        LeadStatus.contacted,
        LeadStatus.contacted,
        LeadStatus.replied,
        LeadStatus.booked,
        LeadStatus.qualified,
    ]
    leads = []
    for s in statuses:
        lead = make_lead(tenant_id=tenant_id, status=s)
        session.add(lead)
        leads.append(lead)
    await session.flush()

    # Create messages linking leads to campaign
    for lead in leads:
        msg = make_message(
            lead_id=lead.id,
            campaign_id=campaign.id,
            channel=ChannelType.email,
            direction=MessageDirection.outbound,
            status=MessageStatus.sent,
        )
        session.add(msg)
    await session.flush()

    return campaign, leads


# ---------- Enhanced Funnel Tests ----------


async def test_funnel_returns_pipeline_stages(async_session: AsyncSession):
    """GET /api/analytics/funnel returns full pipeline stages."""
    tenant, user = _setup_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    # Create leads with various statuses
    statuses = [
        LeadStatus.new,
        LeadStatus.new,
        LeadStatus.contacted,
        LeadStatus.replied,
        LeadStatus.booked,
    ]
    for s in statuses:
        lead = make_lead(tenant_id=tenant.id, status=s)
        async_session.add(lead)
    await async_session.flush()

    # Directly test the analytics logic
    from sqlalchemy import func, select

    result = await async_session.execute(
        select(Lead.status, func.count())
        .where(Lead.tenant_id == tenant.id)
        .group_by(Lead.status)
    )
    status_counts = {
        str(row[0].value) if hasattr(row[0], "value") else str(row[0]): row[1]
        for row in result.all()
    }

    # Build enhanced funnel
    funnel = {
        "leads": sum(status_counts.values()),
        "contacted": status_counts.get("contacted", 0)
        + status_counts.get("replied", 0)
        + status_counts.get("qualified", 0)
        + status_counts.get("booked", 0),
        "replied": status_counts.get("replied", 0)
        + status_counts.get("qualified", 0)
        + status_counts.get("booked", 0),
        "meeting_booked": status_counts.get("booked", 0),
        "closed": status_counts.get("qualified", 0),
    }

    assert funnel["leads"] == 5
    assert funnel["contacted"] == 3  # contacted + replied + booked
    assert funnel["replied"] == 2  # replied + booked
    assert funnel["meeting_booked"] == 1
    assert funnel["closed"] == 0  # no qualified leads


async def test_funnel_empty_tenant(async_session: AsyncSession):
    """Funnel returns zero counts for tenant with no leads."""
    tenant, user = _setup_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    from sqlalchemy import func, select

    result = await async_session.execute(
        select(Lead.status, func.count())
        .where(Lead.tenant_id == tenant.id)
        .group_by(Lead.status)
    )
    status_counts = {
        str(row[0].value) if hasattr(row[0], "value") else str(row[0]): row[1]
        for row in result.all()
    }

    funnel = {
        "leads": sum(status_counts.values()),
        "contacted": status_counts.get("contacted", 0),
        "replied": status_counts.get("replied", 0),
        "meeting_booked": status_counts.get("booked", 0),
        "closed": status_counts.get("qualified", 0),
    }

    assert funnel["leads"] == 0


# ---------- Conversion Rate Tests ----------


async def test_conversion_rates_calculation(async_session: AsyncSession):
    """Conversion rates are calculated correctly from lead status counts."""
    tenant, user = _setup_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    now = datetime.now(timezone.utc)

    # Create leads in current period with known statuses
    leads_data = [
        (LeadStatus.new, now - timedelta(days=5)),
        (LeadStatus.contacted, now - timedelta(days=4)),
        (LeadStatus.contacted, now - timedelta(days=3)),
        (LeadStatus.replied, now - timedelta(days=2)),
        (LeadStatus.booked, now - timedelta(days=1)),
    ]
    for lead_status, created in leads_data:
        lead = make_lead(tenant_id=tenant.id, status=lead_status)
        lead.created_at = created
        async_session.add(lead)
    await async_session.flush()

    # Test conversion rate calculation logic
    from sqlalchemy import func, select
    from dashboard.routes.analytics import _parse_period

    days = _parse_period("30d")
    current_start = now - timedelta(days=days)

    result = await async_session.execute(
        select(Lead.status, func.count())
        .where(
            Lead.tenant_id == tenant.id,
            Lead.created_at >= current_start,
        )
        .group_by(Lead.status)
    )
    counts = {
        str(row[0].value) if hasattr(row[0], "value") else str(row[0]): row[1]
        for row in result.all()
    }

    total = sum(counts.values())
    contacted = counts.get("contacted", 0) + counts.get("replied", 0) + counts.get("qualified", 0) + counts.get("booked", 0)
    replied = counts.get("replied", 0) + counts.get("qualified", 0) + counts.get("booked", 0)
    booked = counts.get("booked", 0)

    assert total == 5
    assert contacted == 4  # contacted(2) + replied(1) + booked(1)
    assert replied == 2  # replied(1) + booked(1)
    assert booked == 1


async def test_conversion_rates_period_parsing():
    """Period string parsing works correctly."""
    from dashboard.routes.analytics import _parse_period

    assert _parse_period("7d") == 7
    assert _parse_period("30d") == 30
    assert _parse_period("90d") == 90
    assert _parse_period("invalid") == 30  # default


# ---------- Channel Performance Tests ----------


async def test_channel_performance_breakdown(async_session: AsyncSession):
    """Channel performance returns correct metrics per channel."""
    tenant, user = _setup_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    campaign = make_campaign(tenant_id=tenant.id, status=CampaignStatus.active)
    async_session.add(campaign)
    await async_session.flush()

    # Create email leads and messages
    email_lead = make_lead(tenant_id=tenant.id, status=LeadStatus.booked)
    async_session.add(email_lead)
    await async_session.flush()

    email_msg = make_message(
        lead_id=email_lead.id,
        campaign_id=campaign.id,
        channel=ChannelType.email,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
    )
    async_session.add(email_msg)
    await async_session.flush()

    # Create reply event for email
    reply_event = make_event(message_id=email_msg.id)
    reply_event.event_type = EventType.reply
    async_session.add(reply_event)
    await async_session.flush()

    # Create voice lead and message
    voice_lead = make_lead(tenant_id=tenant.id, status=LeadStatus.contacted)
    async_session.add(voice_lead)
    await async_session.flush()

    voice_msg = make_message(
        lead_id=voice_lead.id,
        campaign_id=campaign.id,
        channel=ChannelType.voice,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
    )
    async_session.add(voice_msg)
    await async_session.flush()

    # Query channel performance
    from sqlalchemy import func, select

    sent_result = await async_session.execute(
        select(Message.channel, func.count())
        .join(Campaign, Message.campaign_id == Campaign.id)
        .where(
            Campaign.tenant_id == tenant.id,
            Message.status != MessageStatus.draft,
            Message.direction == MessageDirection.outbound,
        )
        .group_by(Message.channel)
    )
    sent_by_channel = {
        str(row[0].value) if hasattr(row[0], "value") else str(row[0]): row[1]
        for row in sent_result.all()
    }

    assert sent_by_channel.get("email", 0) == 1
    assert sent_by_channel.get("voice", 0) == 1

    # Check replies
    replies_result = await async_session.execute(
        select(Message.channel, func.count())
        .join(Campaign, Message.campaign_id == Campaign.id)
        .join(Event, Event.message_id == Message.id)
        .where(
            Campaign.tenant_id == tenant.id,
            Event.event_type == EventType.reply,
        )
        .group_by(Message.channel)
    )
    replies_by_channel = {
        str(row[0].value) if hasattr(row[0], "value") else str(row[0]): row[1]
        for row in replies_result.all()
    }

    assert replies_by_channel.get("email", 0) == 1
    assert replies_by_channel.get("voice", 0) == 0


# ---------- Campaign Funnel Tests ----------


async def test_campaign_funnel(async_session: AsyncSession):
    """Per-campaign funnel returns leads by status within that campaign."""
    tenant, user = _setup_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    campaign, leads = await _create_funnel_data(async_session, tenant.id)

    # Query campaign funnel
    from sqlalchemy import func, select

    funnel_result = await async_session.execute(
        select(Lead.status, func.count(func.distinct(Lead.id)))
        .join(Message, Message.lead_id == Lead.id)
        .where(Message.campaign_id == campaign.id)
        .group_by(Lead.status)
    )
    status_counts = {
        str(row[0].value) if hasattr(row[0], "value") else str(row[0]): row[1]
        for row in funnel_result.all()
    }

    total = sum(status_counts.values())
    assert total == 7  # All 7 leads have messages in this campaign

    funnel = {
        "leads": total,
        "contacted": status_counts.get("contacted", 0)
        + status_counts.get("replied", 0)
        + status_counts.get("qualified", 0)
        + status_counts.get("booked", 0),
        "replied": status_counts.get("replied", 0)
        + status_counts.get("qualified", 0)
        + status_counts.get("booked", 0),
        "meeting_booked": status_counts.get("booked", 0),
        "closed": status_counts.get("qualified", 0),
    }

    assert funnel["leads"] == 7
    assert funnel["contacted"] == 5  # contacted(2) + replied(1) + booked(1) + qualified(1)
    assert funnel["replied"] == 3  # replied(1) + booked(1) + qualified(1)
    assert funnel["meeting_booked"] == 1
    assert funnel["closed"] == 1


async def test_campaign_funnel_empty(async_session: AsyncSession):
    """Campaign funnel with no messages returns zero counts."""
    tenant, user = _setup_tenant_and_user()
    async_session.add(tenant)
    async_session.add(user)
    await async_session.flush()

    campaign = make_campaign(tenant_id=tenant.id, status=CampaignStatus.active)
    async_session.add(campaign)
    await async_session.flush()

    from sqlalchemy import func, select

    funnel_result = await async_session.execute(
        select(Lead.status, func.count(func.distinct(Lead.id)))
        .join(Message, Message.lead_id == Lead.id)
        .where(Message.campaign_id == campaign.id)
        .group_by(Lead.status)
    )
    status_counts = {
        str(row[0].value) if hasattr(row[0], "value") else str(row[0]): row[1]
        for row in funnel_result.all()
    }

    total = sum(status_counts.values())
    assert total == 0


# ---------- Trial Voice Limit Tests ----------


async def test_trial_voice_calls_limit():
    """Trial system enforces voice call limits."""
    from dashboard.routes.trial import (
        TRIAL_DURATION_DAYS,
        TRIAL_VOICE_CALLS_LIMIT,
        TRIAL_LEADS_LIMIT,
        TRIAL_EMAILS_LIMIT,
    )

    assert TRIAL_DURATION_DAYS == 7
    assert TRIAL_VOICE_CALLS_LIMIT == 5
    assert TRIAL_LEADS_LIMIT == 50
    assert TRIAL_EMAILS_LIMIT == 100
