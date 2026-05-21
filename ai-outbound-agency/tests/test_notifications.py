"""Tests for client notifications (weekly digest and real-time alerts)."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

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
)
from integrations.notifications import (
    _get_tenant_notification_config,
    _send_to_channels,
    real_time_alert,
    weekly_digest,
)
from scheduler.notifications_scheduler import NotificationsScheduler
from tests.conftest import make_campaign, make_event, make_lead, make_message, make_tenant


@pytest.fixture
def tenant_with_notifications():
    """Create a tenant with notification channels and preferences configured."""
    return make_tenant(
        settings={
            "notification_channels": [
                {"type": "slack", "webhook_url": "https://hooks.slack.com/test"},
                {"type": "telegram", "bot_token": "bot123", "chat_id": "chat456"},
            ],
            "notification_preferences": {
                "weekly_digest": True,
                "real_time_alerts": True,
                "alert_types": ["positive_reply", "meeting_booked", "pool_depleted"],
            },
        }
    )


async def test_weekly_digest_generates_stats(async_session: AsyncSession, tenant_with_notifications):
    """Test that weekly_digest generates correct stats from DB data."""
    tenant = tenant_with_notifications
    async_session.add(tenant)
    await async_session.flush()

    # Create a campaign for this tenant
    campaign = make_campaign(tenant_id=tenant.id, status=CampaignStatus.active)
    async_session.add(campaign)
    await async_session.flush()

    now = datetime.now(timezone.utc)

    # Create qualified leads this week
    for i in range(3):
        lead = make_lead(
            tenant_id=tenant.id,
            status=LeadStatus.qualified,
            created_at=now - timedelta(days=2),
        )
        async_session.add(lead)

    # Create booked leads this week
    for i in range(2):
        lead = make_lead(
            tenant_id=tenant.id,
            status=LeadStatus.booked,
            created_at=now - timedelta(days=1),
        )
        async_session.add(lead)

    await async_session.flush()

    # Create messages sent this week
    leads_result = await async_session.execute(
        __import__("sqlalchemy").select(Lead).where(Lead.tenant_id == tenant.id)
    )
    leads = leads_result.scalars().all()

    messages = []
    for lead in leads[:3]:
        msg = make_message(
            lead_id=lead.id,
            campaign_id=campaign.id,
            status=MessageStatus.sent,
            sent_at=now - timedelta(days=3),
        )
        async_session.add(msg)
        messages.append(msg)

    await async_session.flush()

    # Create open events for this week
    for msg in messages[:2]:
        evt = make_event(
            message_id=msg.id,
            event_type=EventType.open,
            occurred_at=now - timedelta(days=2),
        )
        async_session.add(evt)

    # Create reply event for this week
    reply_evt = make_event(
        message_id=messages[0].id,
        event_type=EventType.reply,
        occurred_at=now - timedelta(days=1),
    )
    async_session.add(reply_evt)

    await async_session.commit()

    # Mock the _send_to_channels to avoid actual network calls
    with patch("integrations.notifications._send_to_channels", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        stats = await weekly_digest(tenant.id, async_session)

    assert stats["qualified_leads"] == 3
    assert stats["meetings_booked"] == 2
    assert stats["pipeline_value"] == 10000  # 2 * 5000
    assert stats["open_rate"] > 0
    assert stats["reply_rate"] > 0
    assert stats["open_trend"] in ("up", "down")
    assert stats["reply_trend"] in ("up", "down")
    assert stats["top_campaign"] == campaign.name


async def test_real_time_alert_positive_reply(async_session: AsyncSession, tenant_with_notifications):
    """Test that real_time_alert sends notification for positive_reply."""
    tenant = tenant_with_notifications
    async_session.add(tenant)
    await async_session.commit()

    lead_data = {"name": "Jane Smith", "company": "TechCorp"}

    with patch("integrations.notifications._send_to_channels", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        result = await real_time_alert(tenant.id, "positive_reply", lead_data, async_session)

    assert result is True
    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert "Jane Smith" in call_args[0][1]
    assert "TechCorp" in call_args[0][1]


async def test_real_time_alert_respects_preferences(async_session: AsyncSession):
    """Test that alerts not in alert_types are not sent."""
    tenant = make_tenant(
        settings={
            "notification_channels": [
                {"type": "slack", "webhook_url": "https://hooks.slack.com/test"},
            ],
            "notification_preferences": {
                "real_time_alerts": True,
                "alert_types": ["meeting_booked"],  # positive_reply NOT included
            },
        }
    )
    async_session.add(tenant)
    await async_session.commit()

    lead_data = {"name": "John Doe", "company": "Acme"}

    with patch("integrations.notifications._send_to_channels", new_callable=AsyncMock) as mock_send:
        result = await real_time_alert(tenant.id, "positive_reply", lead_data, async_session)

    assert result is False
    mock_send.assert_not_called()


async def test_real_time_alert_no_channels_configured(async_session: AsyncSession):
    """Test that real_time_alert returns False when no channels are configured."""
    tenant = make_tenant(
        settings={
            "notification_channels": [],
            "notification_preferences": {
                "real_time_alerts": True,
                "alert_types": ["positive_reply"],
            },
        }
    )
    async_session.add(tenant)
    await async_session.commit()

    lead_data = {"name": "Test", "company": "TestCo"}

    with patch("integrations.notifications._send_to_channels", new_callable=AsyncMock) as mock_send:
        result = await real_time_alert(tenant.id, "positive_reply", lead_data, async_session)

    assert result is False
    mock_send.assert_not_called()


async def test_send_to_channels_slack():
    """Test that _send_to_channels calls Slack webhook with correct payload."""
    channels = [{"type": "slack", "webhook_url": "https://hooks.slack.com/services/test"}]

    with patch("integrations.notifications.send_slack_notification", new_callable=AsyncMock) as mock_slack:
        mock_slack.return_value = True
        result = await _send_to_channels(channels, "Test message")

    assert result is True
    mock_slack.assert_called_once()
    call_args = mock_slack.call_args
    assert call_args[0][0] == "https://hooks.slack.com/services/test"
    # Blocks should contain the message text
    blocks = call_args[0][1]
    assert blocks[0]["type"] == "section"
    assert "Test message" in blocks[0]["text"]["text"]


async def test_weekly_digest_tick_not_monday(session_factory):
    """Test that weekly_digest_tick does nothing when it's not Monday 9 AM."""
    scheduler = NotificationsScheduler(session_factory=session_factory)

    # Mock datetime to be Tuesday
    tuesday = datetime(2025, 1, 14, 9, 0, 0, tzinfo=timezone.utc)  # Tuesday

    with patch("scheduler.notifications_scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = tuesday
        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        with patch("scheduler.notifications_scheduler.weekly_digest", new_callable=AsyncMock) as mock_digest:
            await scheduler.weekly_digest_tick()
            mock_digest.assert_not_called()


async def test_notifications_scheduler_init(session_factory):
    """Test that NotificationsScheduler can be instantiated."""
    scheduler = NotificationsScheduler(session_factory=session_factory)
    assert scheduler is not None
    assert scheduler._session_factory is session_factory
