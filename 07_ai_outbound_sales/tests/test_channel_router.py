"""Tests for the ChannelRouter."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core.models import (
    ChannelType,
    Event,
    EventType,
    Lead,
    LeadStatus,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
)
from scheduler.channel_router import ChannelRouter
from tests.conftest import make_event, make_lead, make_message, make_tenant


@pytest.fixture
def channel_router(session_factory):
    """Create a ChannelRouter instance with the test session factory."""
    return ChannelRouter(session_factory=session_factory)


async def test_determine_channel_email(channel_router):
    """Step with channel='email' returns 'email'."""
    step_config = {"channel": "email", "delay_days": 1}
    assert channel_router.determine_channel(step_config) == "email"


async def test_determine_channel_linkedin(channel_router):
    """Step with channel='linkedin_connect' returns 'linkedin_connect'."""
    step_config = {"channel": "linkedin_connect", "delay_days": 2}
    assert channel_router.determine_channel(step_config) == "linkedin_connect"


async def test_determine_channel_legacy(channel_router):
    """Step with step_type='initial' but no channel field returns 'email'."""
    step_config = {"step_type": "initial", "delay_days": 0}
    assert channel_router.determine_channel(step_config) == "email"


async def test_should_skip_lead_replied(channel_router, async_session):
    """Lead with status=replied is skipped."""
    tenant = make_tenant()
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant.id, status=LeadStatus.replied)
    async_session.add(lead)
    await async_session.flush()

    campaign_id = uuid.uuid4()
    result = await channel_router.should_skip_lead(lead.id, campaign_id, async_session)
    assert result is True


async def test_should_skip_lead_active(channel_router, async_session):
    """Lead with status=new is not skipped."""
    tenant = make_tenant()
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant.id, status=LeadStatus.new)
    async_session.add(lead)
    await async_session.flush()

    campaign_id = uuid.uuid4()
    result = await channel_router.should_skip_lead(lead.id, campaign_id, async_session)
    assert result is False


async def test_calculate_delay_basic(channel_router, async_session):
    """Returns timedelta(days=delay_days) for non-linkedin_connect steps."""
    tenant = make_tenant()
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)
    await async_session.flush()

    campaign_id = uuid.uuid4()
    step_config = {"channel": "email", "delay_days": 3}
    delay = await channel_router.calculate_delay(step_config, lead.id, campaign_id, async_session)
    assert delay == timedelta(days=3)


async def test_calculate_delay_linkedin_with_open(channel_router, async_session):
    """If lead has email open event, adds 2 extra days for linkedin_connect."""
    tenant = make_tenant()
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)

    # Need a real campaign in the DB for FK constraint
    from tests.conftest import make_campaign
    campaign = make_campaign(tenant_id=tenant.id)
    async_session.add(campaign)
    await async_session.flush()

    campaign_id = campaign.id

    # Create an email message for this lead+campaign
    email_msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign_id,
        channel=ChannelType.email,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
    )
    async_session.add(email_msg)
    await async_session.flush()

    # Create an open event for that email message
    open_event = make_event(message_id=email_msg.id, event_type=EventType.open)
    async_session.add(open_event)
    await async_session.flush()

    step_config = {"channel": "linkedin_connect", "delay_days": 3}
    delay = await channel_router.calculate_delay(step_config, lead.id, campaign_id, async_session)
    assert delay == timedelta(days=5)  # 3 + 2 extra


async def test_check_prerequisites_linkedin_message_no_connect(channel_router, async_session):
    """Returns False if no prior linkedin_connect message sent."""
    tenant = make_tenant()
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)
    await async_session.flush()

    step_config = {"channel": "linkedin_message", "delay_days": 1}
    result = await channel_router.check_prerequisites(step_config, lead.id, async_session)
    assert result is False


async def test_check_prerequisites_linkedin_message_with_connect(channel_router, async_session):
    """Returns True if prior linkedin_connect message was sent."""
    tenant = make_tenant()
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)

    # Need a real campaign in the DB for FK constraint
    from tests.conftest import make_campaign
    campaign = make_campaign(tenant_id=tenant.id)
    async_session.add(campaign)
    await async_session.flush()

    campaign_id = campaign.id

    # Create a linkedin_connect message for this lead
    connect_msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign_id,
        channel=ChannelType.linkedin,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        meta={"linkedin_task": "linkedin_connect_task", "profile_url": "https://linkedin.com/in/test"},
    )
    async_session.add(connect_msg)
    await async_session.flush()

    step_config = {"channel": "linkedin_message", "delay_days": 1}
    result = await channel_router.check_prerequisites(step_config, lead.id, async_session)
    assert result is True
