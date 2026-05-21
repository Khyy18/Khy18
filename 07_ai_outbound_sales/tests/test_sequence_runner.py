"""Tests for the SequenceRunner."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.models import (
    Campaign,
    CampaignStatus,
    ChannelType,
    Lead,
    LeadStatus,
    Message,
    MessageDirection,
    MessageStatus,
    Sequence,
    Tenant,
)
from scheduler.sequence_runner import SequenceRunner
from tests.conftest import make_campaign, make_lead, make_message, make_sequence, make_tenant


@pytest.fixture
def mock_tracker():
    tracker = MagicMock()
    tracker.generate_tracking_pixel_url = MagicMock(return_value="http://track.example.com/pixel/123")
    tracker.generate_click_url = MagicMock(return_value="http://track.example.com/click/123")
    return tracker


@pytest.fixture
def mock_copywriter():
    cw = AsyncMock()
    cw.write_message = AsyncMock(return_value={
        "subject": "Test Subject",
        "body": "<p>Test body</p>",
        "step_type": "initial",
    })
    return cw


@pytest.fixture
def sequence_runner(session_factory, mock_email_sender, mock_copywriter, mock_tracker):
    runner = SequenceRunner(
        session_factory=session_factory,
        redis_url="redis://localhost:6379/0",
        email_sender=mock_email_sender,
        copywriter=mock_copywriter,
        tracker=mock_tracker,
    )
    return runner


async def test_count_sent_messages(sequence_runner, async_session):
    """Test _count_sent_messages returns correct count."""
    tenant_id = uuid.uuid4()
    tenant = make_tenant(id=tenant_id)
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant_id)
    async_session.add(lead)

    campaign = make_campaign(tenant_id=tenant_id)
    async_session.add(campaign)
    await async_session.flush()

    # Add 3 sent messages
    for _ in range(3):
        msg = make_message(
            lead_id=lead.id,
            campaign_id=campaign.id,
            direction=MessageDirection.outbound,
            status=MessageStatus.sent,
        )
        async_session.add(msg)

    # Add 1 draft message (should not be counted)
    draft = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.outbound,
        status=MessageStatus.draft,
    )
    async_session.add(draft)

    # Add 1 inbound message (should not be counted)
    inbound = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.inbound,
        status=MessageStatus.sent,
    )
    async_session.add(inbound)
    await async_session.flush()

    count = await sequence_runner._count_sent_messages(async_session, campaign.id, lead.id)
    assert count == 3


async def test_leads_with_skip_statuses_are_filtered(sequence_runner, async_session):
    """Test leads with replied/lost/booked status are skipped."""
    tenant_id = uuid.uuid4()
    tenant = make_tenant(id=tenant_id)
    async_session.add(tenant)

    campaign = make_campaign(tenant_id=tenant_id, status=CampaignStatus.active)
    async_session.add(campaign)
    await async_session.flush()

    # Create leads with various statuses
    active_lead = make_lead(tenant_id=tenant_id, status=LeadStatus.new)
    replied_lead = make_lead(tenant_id=tenant_id, status=LeadStatus.replied)
    lost_lead = make_lead(tenant_id=tenant_id, status=LeadStatus.lost)
    booked_lead = make_lead(tenant_id=tenant_id, status=LeadStatus.booked)

    for lead in [active_lead, replied_lead, lost_lead, booked_lead]:
        async_session.add(lead)
    await async_session.flush()

    # Add messages linking leads to campaign
    for lead in [active_lead, replied_lead, lost_lead, booked_lead]:
        msg = make_message(lead_id=lead.id, campaign_id=campaign.id)
        async_session.add(msg)
    await async_session.flush()

    leads = await sequence_runner._get_campaign_leads(async_session, campaign)

    # Only new/contacted leads should be returned (not replied/lost/booked)
    lead_ids = [l.id for l in leads]
    assert active_lead.id in lead_ids
    assert replied_lead.id not in lead_ids
    assert lost_lead.id not in lead_ids
    assert booked_lead.id not in lead_ids


async def test_delay_calculation_respects_delay_days(sequence_runner, async_session):
    """Test that a step with delay_days=3 is not sent before 3 days have passed."""
    tenant_id = uuid.uuid4()
    tenant = make_tenant(id=tenant_id)
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant_id, status=LeadStatus.contacted)
    async_session.add(lead)

    campaign = make_campaign(tenant_id=tenant_id, status=CampaignStatus.active)
    async_session.add(campaign)

    sequence = make_sequence(tenant_id=tenant_id, steps=[
        {"step_type": "initial", "delay_days": 0},
        {"step_type": "follow_up_1", "delay_days": 3},
    ])
    async_session.add(sequence)
    await async_session.flush()

    campaign.sequence_id = sequence.id
    await async_session.flush()

    # Create message sent only 1 day ago (less than 3 days delay)
    one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.outbound,
        status=MessageStatus.sent,
        sent_at=one_day_ago,
    )
    async_session.add(msg)
    await async_session.flush()

    # _process_lead should NOT send because delay hasn't elapsed
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock()
    sequence_runner._redis = mock_redis

    steps = sequence.steps
    await sequence_runner._process_lead(async_session, campaign, lead, steps)

    # The email sender should not have been called (delay not met)
    sequence_runner._email_sender.send_email.assert_not_called()


async def test_distributed_lock_prevents_double_send(sequence_runner, async_session):
    """Test distributed lock prevents double-send (mock Redis set with nx=True returning False)."""
    tenant_id = uuid.uuid4()
    tenant = make_tenant(id=tenant_id)
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant_id, status=LeadStatus.new)
    async_session.add(lead)

    campaign = make_campaign(tenant_id=tenant_id, status=CampaignStatus.active)
    async_session.add(campaign)
    await async_session.flush()

    # Mock Redis to simulate lock not acquired
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=False)  # Lock already held
    mock_redis.delete = AsyncMock()
    sequence_runner._redis = mock_redis

    steps = [{"step_type": "initial", "delay_days": 0}]
    await sequence_runner._process_lead(async_session, campaign, lead, steps)

    # Email should not be sent because lock was not acquired
    sequence_runner._email_sender.send_email.assert_not_called()


async def test_linkedin_step_does_not_call_email_sender(sequence_runner, async_session):
    """Test that a linkedin_connect step does not call email_sender.send_email."""
    tenant_id = uuid.uuid4()
    tenant = make_tenant(id=tenant_id)
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant_id, status=LeadStatus.new, linkedin_url="https://linkedin.com/in/testuser")
    async_session.add(lead)

    campaign = make_campaign(tenant_id=tenant_id, status=CampaignStatus.active)
    async_session.add(campaign)
    await async_session.flush()

    # Mock Redis to allow lock
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock()
    sequence_runner._redis = mock_redis

    steps = [{"channel": "linkedin_connect", "delay_days": 0}]

    # Patch the usage limiter to allow
    with patch("compliance.usage_limiter.get_usage_limiter") as mock_limiter_fn:
        mock_limiter = AsyncMock()
        mock_limiter.check_and_increment = AsyncMock(return_value=True)
        mock_limiter_fn.return_value = mock_limiter

        await sequence_runner._process_lead(async_session, campaign, lead, steps)

    # Email sender should NOT have been called
    sequence_runner._email_sender.send_email.assert_not_called()
