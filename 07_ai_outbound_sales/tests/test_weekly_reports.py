"""Tests for weekly reports feature."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
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
)
from integrations.weekly_report import WeeklyReportGenerator, format_telegram_report

# Import factory functions from conftest
from tests.conftest import (
    make_campaign,
    make_event,
    make_lead,
    make_message,
    make_tenant,
    make_user,
)


# ---------- Report Generation Tests ----------


async def test_generate_report_computes_metrics(async_session: AsyncSession):
    """Test that generate_report computes correct metrics from test data."""
    now = datetime.now(timezone.utc)
    this_week = now - timedelta(days=2)

    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    campaign = make_campaign(tenant_id=tenant.id)
    async_session.add(campaign)
    await async_session.flush()

    # Create leads with various statuses this week
    lead_contacted = make_lead(
        tenant_id=tenant.id,
        status=LeadStatus.contacted,
        created_at=this_week,
    )
    lead_booked = make_lead(
        tenant_id=tenant.id,
        status=LeadStatus.booked,
        created_at=this_week,
    )
    lead_hot = make_lead(
        tenant_id=tenant.id,
        status=LeadStatus.qualified,
        score=85.0,
        created_at=this_week,
    )
    lead_new = make_lead(
        tenant_id=tenant.id,
        status=LeadStatus.new,
        created_at=this_week,
    )
    async_session.add_all([lead_contacted, lead_booked, lead_hot, lead_new])
    await async_session.flush()

    # Create email messages sent this week
    msg1 = make_message(
        lead_id=lead_contacted.id,
        campaign_id=campaign.id,
        channel=ChannelType.email,
        status=MessageStatus.sent,
        sent_at=this_week,
    )
    msg2 = make_message(
        lead_id=lead_booked.id,
        campaign_id=campaign.id,
        channel=ChannelType.email,
        status=MessageStatus.sent,
        sent_at=this_week,
    )
    async_session.add_all([msg1, msg2])
    await async_session.flush()

    # Create events
    event_open = make_event(
        message_id=msg1.id,
        event_type=EventType.open,
        occurred_at=this_week,
    )
    event_reply = make_event(
        message_id=msg2.id,
        event_type=EventType.reply,
        occurred_at=this_week,
    )
    async_session.add_all([event_open, event_reply])
    await async_session.flush()

    generator = WeeklyReportGenerator()
    report = await generator.generate_report(tenant.id, async_session)

    metrics = report["metrics"]

    # leads_contacted: 3 (contacted, booked, qualified - all not 'new')
    assert metrics["leads_contacted"]["current"] == 3
    # emails_sent: 2
    assert metrics["emails_sent"]["current"] == 2
    # open_rate: 1 open / 2 emails * 100 = 50.0
    assert metrics["open_rate"]["current"] == 50.0
    # reply_rate: 1 reply / 2 emails * 100 = 50.0
    assert metrics["reply_rate"]["current"] == 50.0
    # meetings_booked: 1
    assert metrics["meetings_booked"]["current"] == 1
    # hot_leads: 1 (score >= 70)
    assert metrics["hot_leads"]["current"] == 1


async def test_generate_report_delta_percent(async_session: AsyncSession):
    """Test that delta_percent is computed correctly for positive and negative changes."""
    now = datetime.now(timezone.utc)
    this_week = now - timedelta(days=2)
    last_week = now - timedelta(days=10)

    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    campaign = make_campaign(tenant_id=tenant.id)
    async_session.add(campaign)
    await async_session.flush()

    # Previous week: 4 contacted leads
    for _ in range(4):
        lead = make_lead(
            tenant_id=tenant.id,
            status=LeadStatus.contacted,
            created_at=last_week,
        )
        async_session.add(lead)

    # This week: 2 contacted leads (decline)
    for _ in range(2):
        lead = make_lead(
            tenant_id=tenant.id,
            status=LeadStatus.contacted,
            created_at=this_week,
        )
        async_session.add(lead)

    await async_session.flush()

    generator = WeeklyReportGenerator()
    report = await generator.generate_report(tenant.id, async_session)

    metrics = report["metrics"]
    # delta_percent = ((2 - 4) / 4) * 100 = -50.0
    assert metrics["leads_contacted"]["current"] == 2
    assert metrics["leads_contacted"]["previous"] == 4
    assert metrics["leads_contacted"]["delta_percent"] == -50.0


async def test_generate_report_no_data(async_session: AsyncSession):
    """Test that empty tenant returns zeros for all metrics."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    generator = WeeklyReportGenerator()
    report = await generator.generate_report(tenant.id, async_session)

    metrics = report["metrics"]
    assert metrics["leads_contacted"]["current"] == 0
    assert metrics["leads_contacted"]["previous"] == 0
    assert metrics["leads_contacted"]["delta_percent"] == 0.0
    assert metrics["emails_sent"]["current"] == 0
    assert metrics["open_rate"]["current"] == 0.0
    assert metrics["reply_rate"]["current"] == 0.0
    assert metrics["meetings_booked"]["current"] == 0
    assert metrics["hot_leads"]["current"] == 0


# ---------- Preferences Tests ----------


async def test_preferences_update(async_session: AsyncSession):
    """Test that updating preferences stores values in tenant settings."""
    tenant = make_tenant(settings={})
    async_session.add(tenant)
    await async_session.flush()

    # Simulate what the endpoint does: store preferences in tenant.settings
    settings_data = dict(tenant.settings or {})
    settings_data["report_preferences"] = {
        "delivery_method": "both",
        "email_address": "reports@example.com",
        "telegram_chat_id": "12345",
    }
    tenant.settings = settings_data
    await async_session.flush()

    # Verify stored in DB
    result = await async_session.execute(
        select(Tenant).where(Tenant.id == tenant.id)
    )
    refreshed = result.scalar_one()
    prefs = refreshed.settings["report_preferences"]
    assert prefs["delivery_method"] == "both"
    assert prefs["email_address"] == "reports@example.com"
    assert prefs["telegram_chat_id"] == "12345"


async def test_preferences_get(async_session: AsyncSession):
    """Test that reading preferences returns stored values."""
    tenant = make_tenant(
        settings={
            "report_preferences": {
                "delivery_method": "email",
                "email_address": "user@test.com",
                "telegram_chat_id": "",
            }
        }
    )
    async_session.add(tenant)
    await async_session.flush()

    # Simulate what the GET endpoint does: read from tenant.settings
    result = await async_session.execute(
        select(Tenant).where(Tenant.id == tenant.id)
    )
    loaded_tenant = result.scalar_one()
    preferences = loaded_tenant.settings.get("report_preferences", {})

    assert preferences["delivery_method"] == "email"
    assert preferences["email_address"] == "user@test.com"
    assert preferences["telegram_chat_id"] == ""


# ---------- Telegram Format Test ----------


async def test_format_telegram_report():
    """Test that format_telegram_report produces correct markdown format."""
    report_data = {
        "period": "Jun 01 - Jun 07, 2025",
        "metrics": {
            "leads_contacted": {"current": 50, "previous": 40, "delta_percent": 25.0},
            "emails_sent": {"current": 200, "previous": 180, "delta_percent": 11.1},
            "open_rate": {"current": 45.5, "previous": 42.0, "delta_percent": 8.3},
            "reply_rate": {"current": 8.2, "previous": 10.0, "delta_percent": -18.0},
            "meetings_booked": {"current": 5, "previous": 3, "delta_percent": 66.7},
            "hot_leads": {"current": 12, "previous": 8, "delta_percent": 50.0},
        },
    }

    result = format_telegram_report(report_data)

    assert "*Weekly Performance Report*" in result
    assert "Jun 01 - Jun 07, 2025" in result
    assert "*Leads Contacted:*" in result
    assert "*Emails Sent:*" in result
    assert "*Open Rate:*" in result
    assert "*Reply Rate:*" in result
    assert "*Meetings Booked:*" in result
    assert "*Hot Leads:*" in result
    # Check positive delta arrow (upward arrow emoji)
    assert "\u2b06\ufe0f" in result
    # Check negative delta arrow (downward arrow emoji for reply_rate)
    assert "\u2b07\ufe0f" in result


# ---------- Delivery Tests ----------


async def test_deliver_report_email(async_session: AsyncSession):
    """Test that deliver_report calls send_email_digest with HTML when method is email."""
    tenant = make_tenant(
        settings={
            "report_preferences": {
                "delivery_method": "email",
                "email_address": "test@example.com",
                "telegram_chat_id": "",
            }
        }
    )
    async_session.add(tenant)
    await async_session.flush()

    report_data = {
        "tenant_id": str(tenant.id),
        "period": "Jun 01 - Jun 07, 2025",
        "generated_at": "2025-06-07T12:00:00+00:00",
        "metrics": {
            "leads_contacted": {"current": 10, "previous": 5, "delta_percent": 100.0},
            "emails_sent": {"current": 50, "previous": 40, "delta_percent": 25.0},
            "open_rate": {"current": 30.0, "previous": 25.0, "delta_percent": 20.0},
            "reply_rate": {"current": 5.0, "previous": 4.0, "delta_percent": 25.0},
            "meetings_booked": {"current": 2, "previous": 1, "delta_percent": 100.0},
            "hot_leads": {"current": 3, "previous": 2, "delta_percent": 50.0},
        },
    }

    generator = WeeklyReportGenerator()

    with patch(
        "integrations.notifications.send_email_digest", new_callable=AsyncMock
    ) as mock_send:
        mock_send.return_value = True
        result = await generator.deliver_report(tenant.id, report_data, async_session)

    assert result["success"] is True
    assert "email" in result["delivered_via"]
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args
    assert call_kwargs[1]["to_email"] == "test@example.com"
    assert "Weekly Performance Report" in call_kwargs[1]["subject"]
    # Check HTML content was rendered
    html_body = call_kwargs[1]["html_body"]
    assert "<!DOCTYPE html>" in html_body or "<!doctype html>" in html_body.lower()


async def test_deliver_report_telegram(async_session: AsyncSession):
    """Test that deliver_report calls send_telegram_notification when method is telegram."""
    tenant = make_tenant(
        settings={
            "report_preferences": {
                "delivery_method": "telegram",
                "email_address": "",
                "telegram_chat_id": "999888",
            }
        }
    )
    async_session.add(tenant)
    await async_session.flush()

    report_data = {
        "tenant_id": str(tenant.id),
        "period": "Jun 01 - Jun 07, 2025",
        "generated_at": "2025-06-07T12:00:00+00:00",
        "metrics": {
            "leads_contacted": {"current": 10, "previous": 5, "delta_percent": 100.0},
            "emails_sent": {"current": 50, "previous": 40, "delta_percent": 25.0},
            "open_rate": {"current": 30.0, "previous": 25.0, "delta_percent": 20.0},
            "reply_rate": {"current": 5.0, "previous": 4.0, "delta_percent": 25.0},
            "meetings_booked": {"current": 2, "previous": 1, "delta_percent": 100.0},
            "hot_leads": {"current": 3, "previous": 2, "delta_percent": 50.0},
        },
    }

    generator = WeeklyReportGenerator()

    with patch(
        "integrations.notifications.send_telegram_notification",
        new_callable=AsyncMock,
    ) as mock_send:
        mock_send.return_value = True
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "fake-token"}):
            result = await generator.deliver_report(
                tenant.id, report_data, async_session
            )

    assert result["success"] is True
    assert "telegram" in result["delivered_via"]
    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert call_args[1]["chat_id"] == "999888"
    assert "*Weekly Performance Report*" in call_args[1]["text"]
