"""Notification integrations - Slack and Telegram for human-in-the-loop alerts."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import (
    Campaign,
    CampaignStatus,
    Event,
    EventType,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
    Tenant,
)

logger = logging.getLogger(__name__)


async def send_slack_notification(
    webhook_url: str,
    message_blocks: list[dict[str, Any]],
) -> bool:
    """Send a notification to Slack via an incoming webhook.

    Args:
        webhook_url: The Slack webhook URL.
        message_blocks: A list of Slack Block Kit blocks.

    Returns:
        True if the notification was sent successfully, False otherwise.
    """
    if not webhook_url:
        logger.warning("Slack webhook URL not configured, skipping notification")
        return False

    payload = {"blocks": message_blocks}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
            if response.status_code == 200:
                logger.info("Slack notification sent successfully")
                return True
            logger.warning(
                "Slack webhook returned status %d: %s",
                response.status_code,
                response.text,
            )
            return False
    except httpx.HTTPError as exc:
        logger.error("Failed to send Slack notification: %s", exc)
        return False


async def send_telegram_notification(
    bot_token: str,
    chat_id: str,
    text: str,
) -> bool:
    """Send a notification via Telegram Bot API.

    Args:
        bot_token: The Telegram bot token.
        chat_id: The Telegram chat ID to send to.
        text: The message text (supports Markdown).

    Returns:
        True if the notification was sent successfully, False otherwise.
    """
    if not bot_token or not chat_id:
        logger.warning("Telegram bot_token or chat_id not configured, skipping notification")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            data = response.json()
            if data.get("ok"):
                logger.info("Telegram notification sent successfully")
                return True
            logger.warning("Telegram API error: %s", data.get("description", "Unknown"))
            return False
    except httpx.HTTPError as exc:
        logger.error("Failed to send Telegram notification: %s", exc)
        return False


async def notify_human(
    lead_data: dict[str, Any],
    classification: str,
    proposed_response: dict[str, Any],
    settings: Any,
) -> None:
    """Unified notification function that sends alerts to configured channels.

    Sends a formatted notification to Slack and/or Telegram based on
    which channels are configured in settings.

    Args:
        lead_data: Dictionary with lead information (name, email, company, title).
        classification: The reply classification (e.g. 'positive', 'objection').
        proposed_response: The AI-generated proposed response dict.
        settings: Application settings object with notification config.
    """
    lead_name = f"{lead_data.get('first_name', '')} {lead_data.get('last_name', '')}".strip()
    lead_company = lead_data.get("company", "Unknown")
    lead_title = lead_data.get("title", "Unknown")
    lead_email = lead_data.get("email", "Unknown")

    # Send Slack notification
    slack_success = True
    if settings.slack_webhook_url:
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Approval Required: New Reply",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Lead:* {lead_name}"},
                    {"type": "mrkdwn", "text": f"*Company:* {lead_company}"},
                    {"type": "mrkdwn", "text": f"*Title:* {lead_title}"},
                    {"type": "mrkdwn", "text": f"*Email:* {lead_email}"},
                    {"type": "mrkdwn", "text": f"*Classification:* {classification}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Proposed Subject:* {proposed_response.get('subject', 'N/A')}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Proposed Action:* {proposed_response.get('action', 'N/A')}",
                },
            },
        ]
        slack_success = await send_slack_notification(settings.slack_webhook_url, blocks)
        if not slack_success:
            logger.warning(
                "Failed to send Slack notification for lead %s (classification=%s). "
                "Approval was still created but human may not be alerted.",
                lead_email,
                classification,
            )

    # Send Telegram notification
    telegram_success = True
    if settings.telegram_bot_token and settings.telegram_chat_id:
        text = (
            f"*Approval Required*\n\n"
            f"*Lead:* {lead_name}\n"
            f"*Company:* {lead_company}\n"
            f"*Title:* {lead_title}\n"
            f"*Email:* {lead_email}\n"
            f"*Classification:* {classification}\n\n"
            f"*Proposed Subject:* {proposed_response.get('subject', 'N/A')}\n"
            f"*Action:* {proposed_response.get('action', 'N/A')}"
        )
        telegram_success = await send_telegram_notification(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            text,
        )
        if not telegram_success:
            logger.warning(
                "Failed to send Telegram notification for lead %s (classification=%s). "
                "Approval was still created but human may not be alerted.",
                lead_email,
                classification,
            )

    if not slack_success and not telegram_success:
        logger.warning(
            "All notification channels failed for lead %s. Human review required but no alert was delivered.",
            lead_email,
        )


# ---------- Tenant Notification Config Helpers ----------


async def _get_tenant_notification_config(
    tenant_id: UUID, session: AsyncSession
) -> tuple[list[dict], dict]:
    """Get notification_channels and notification_preferences from tenant settings.

    Returns (channels_list, preferences_dict).
    channels_list items: {"type": "slack", "webhook_url": "..."} or
        {"type": "telegram", "chat_id": "...", "bot_token": "..."} or
        {"type": "email", "address": "..."}
    preferences_dict: {"weekly_digest": True, "real_time_alerts": True,
        "alert_types": ["positive_reply", "meeting_booked"]}
    """
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return [], {}

    settings = tenant.settings or {}
    channels: list[dict] = settings.get("notification_channels", [])
    preferences: dict = settings.get("notification_preferences", {})
    return channels, preferences


async def _send_to_channels(
    channels: list[dict], message_text: str, blocks: list[dict] | None = None
) -> bool:
    """Send notification to all configured channels. Returns True if any succeeded."""
    if not channels:
        return False

    any_success = False
    for channel in channels:
        channel_type = channel.get("type", "")
        try:
            if channel_type == "slack":
                webhook_url = channel.get("webhook_url", "")
                send_blocks = blocks or [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": message_text},
                    }
                ]
                success = await send_slack_notification(webhook_url, send_blocks)
                if success:
                    any_success = True
            elif channel_type == "telegram":
                bot_token = channel.get("bot_token", "")
                chat_id = channel.get("chat_id", "")
                success = await send_telegram_notification(bot_token, chat_id, message_text)
                if success:
                    any_success = True
            elif channel_type == "email":
                address = channel.get("address", "")
                if address:
                    success = await send_email_digest(
                        to_email=address,
                        subject="Notification",
                        html_body=f"<p>{message_text}</p>",
                    )
                    if success:
                        any_success = True
            else:
                logger.warning("Unknown notification channel type: %s", channel_type)
        except Exception as exc:
            logger.error("Failed to send to channel %s: %s", channel_type, exc)

    return any_success


# ---------- Email Digest ----------


async def send_email_digest(to_email: str, subject: str, html_body: str) -> bool:
    """Send an email digest notification via SMTP.

    Uses aiosmtplib for sending. Falls back gracefully on error.
    """
    import os

    smtp_host = os.environ.get("SMTP_HOST", "localhost")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_from = os.environ.get("SMTP_FROM", "noreply@example.com")

    try:
        import aiosmtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user or None,
            password=smtp_pass or None,
            start_tls=True,
        )
        logger.info("Email digest sent to %s", to_email)
        return True
    except Exception as exc:
        logger.error("Failed to send email digest to %s: %s", to_email, exc)
        return False


# ---------- Weekly Digest ----------


async def weekly_digest(tenant_id: UUID, session: AsyncSession) -> dict[str, Any]:
    """Generate and send weekly digest for a tenant.

    Queries the past 7 days for:
    - Qualified leads count (leads with status 'qualified' created this week)
    - Meetings booked count (leads with status 'booked' this week)
    - Pipeline value estimate (meetings_booked * 5000 as rough estimate)
    - Top performing campaign (highest reply rate)
    - Open rate and reply rate trends (this week vs previous week, up/down)

    Sends digest to all configured notification channels for the tenant.
    Returns dict with stats computed.
    """
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    # Qualified leads this week
    qualified_result = await session.execute(
        select(func.count(Lead.id)).where(
            Lead.tenant_id == tenant_id,
            Lead.status == LeadStatus.qualified,
            Lead.created_at >= week_ago,
        )
    )
    qualified_count = qualified_result.scalar() or 0

    # Meetings booked this week
    booked_result = await session.execute(
        select(func.count(Lead.id)).where(
            Lead.tenant_id == tenant_id,
            Lead.status == LeadStatus.booked,
            Lead.created_at >= week_ago,
        )
    )
    meetings_booked = booked_result.scalar() or 0

    # Pipeline value estimate
    pipeline_value = meetings_booked * 5000

    # Messages sent this week (for rate calculations)
    this_week_sent_result = await session.execute(
        select(func.count(Message.id)).where(
            Message.campaign_id.in_(
                select(Campaign.id).where(Campaign.tenant_id == tenant_id)
            ),
            Message.sent_at >= week_ago,
            Message.status != MessageStatus.draft,
        )
    )
    this_week_sent = this_week_sent_result.scalar() or 0

    # Opens this week
    this_week_opens_result = await session.execute(
        select(func.count(Event.id)).where(
            Event.event_type == EventType.open,
            Event.occurred_at >= week_ago,
            Event.message_id.in_(
                select(Message.id).where(
                    Message.campaign_id.in_(
                        select(Campaign.id).where(Campaign.tenant_id == tenant_id)
                    )
                )
            ),
        )
    )
    this_week_opens = this_week_opens_result.scalar() or 0

    # Replies this week
    this_week_replies_result = await session.execute(
        select(func.count(Event.id)).where(
            Event.event_type == EventType.reply,
            Event.occurred_at >= week_ago,
            Event.message_id.in_(
                select(Message.id).where(
                    Message.campaign_id.in_(
                        select(Campaign.id).where(Campaign.tenant_id == tenant_id)
                    )
                )
            ),
        )
    )
    this_week_replies = this_week_replies_result.scalar() or 0

    # Previous week sent (for trend)
    prev_week_sent_result = await session.execute(
        select(func.count(Message.id)).where(
            Message.campaign_id.in_(
                select(Campaign.id).where(Campaign.tenant_id == tenant_id)
            ),
            Message.sent_at >= two_weeks_ago,
            Message.sent_at < week_ago,
            Message.status != MessageStatus.draft,
        )
    )
    prev_week_sent = prev_week_sent_result.scalar() or 0

    # Previous week opens
    prev_week_opens_result = await session.execute(
        select(func.count(Event.id)).where(
            Event.event_type == EventType.open,
            Event.occurred_at >= two_weeks_ago,
            Event.occurred_at < week_ago,
            Event.message_id.in_(
                select(Message.id).where(
                    Message.campaign_id.in_(
                        select(Campaign.id).where(Campaign.tenant_id == tenant_id)
                    )
                )
            ),
        )
    )
    prev_week_opens = prev_week_opens_result.scalar() or 0

    # Previous week replies
    prev_week_replies_result = await session.execute(
        select(func.count(Event.id)).where(
            Event.event_type == EventType.reply,
            Event.occurred_at >= two_weeks_ago,
            Event.occurred_at < week_ago,
            Event.message_id.in_(
                select(Message.id).where(
                    Message.campaign_id.in_(
                        select(Campaign.id).where(Campaign.tenant_id == tenant_id)
                    )
                )
            ),
        )
    )
    prev_week_replies = prev_week_replies_result.scalar() or 0

    # Calculate rates
    open_rate = (this_week_opens / this_week_sent * 100) if this_week_sent > 0 else 0.0
    reply_rate = (this_week_replies / this_week_sent * 100) if this_week_sent > 0 else 0.0
    prev_open_rate = (prev_week_opens / prev_week_sent * 100) if prev_week_sent > 0 else 0.0
    prev_reply_rate = (prev_week_replies / prev_week_sent * 100) if prev_week_sent > 0 else 0.0

    open_trend = "up" if open_rate > prev_open_rate else "down"
    reply_trend = "up" if reply_rate > prev_reply_rate else "down"

    # Top performing campaign (highest reply rate this week)
    top_campaign_name = "N/A"
    campaigns_result = await session.execute(
        select(Campaign).where(
            Campaign.tenant_id == tenant_id,
            Campaign.status == CampaignStatus.active,
        )
    )
    campaigns = campaigns_result.scalars().all()

    best_rate = -1.0
    for campaign in campaigns:
        camp_sent_result = await session.execute(
            select(func.count(Message.id)).where(
                Message.campaign_id == campaign.id,
                Message.sent_at >= week_ago,
                Message.status != MessageStatus.draft,
            )
        )
        camp_sent = camp_sent_result.scalar() or 0
        if camp_sent == 0:
            continue
        camp_replies_result = await session.execute(
            select(func.count(Event.id)).where(
                Event.event_type == EventType.reply,
                Event.occurred_at >= week_ago,
                Event.message_id.in_(
                    select(Message.id).where(Message.campaign_id == campaign.id)
                ),
            )
        )
        camp_replies = camp_replies_result.scalar() or 0
        camp_reply_rate = camp_replies / camp_sent
        if camp_reply_rate > best_rate:
            best_rate = camp_reply_rate
            top_campaign_name = campaign.name

    stats = {
        "qualified_leads": qualified_count,
        "meetings_booked": meetings_booked,
        "pipeline_value": pipeline_value,
        "top_campaign": top_campaign_name,
        "open_rate": round(open_rate, 1),
        "reply_rate": round(reply_rate, 1),
        "open_trend": open_trend,
        "reply_trend": reply_trend,
    }

    # Send digest to configured channels
    channels, preferences = await _get_tenant_notification_config(tenant_id, session)
    if preferences.get("weekly_digest", True) and channels:
        digest_text = (
            f"Weekly Digest:\n"
            f"- Qualified Leads: {qualified_count}\n"
            f"- Meetings Booked: {meetings_booked}\n"
            f"- Pipeline Value: ${pipeline_value:,}\n"
            f"- Top Campaign: {top_campaign_name}\n"
            f"- Open Rate: {open_rate:.1f}% ({open_trend})\n"
            f"- Reply Rate: {reply_rate:.1f}% ({reply_trend})"
        )
        try:
            await _send_to_channels(channels, digest_text)
        except Exception as exc:
            logger.error("Failed to send weekly digest for tenant %s: %s", tenant_id, exc)

    return stats


# ---------- Real-Time Alert ----------


async def real_time_alert(
    tenant_id: UUID,
    event_type: str,
    lead_data: dict[str, Any],
    session: AsyncSession,
) -> bool:
    """Send a real-time alert for a significant event.

    Event types:
    - "positive_reply": "New positive reply from {name} at {company}"
    - "meeting_booked": "Meeting booked with {name} at {company}"
    - "pool_depleted": "Campaign {campaign_name} depleted lead pool"

    Checks tenant notification_preferences to see if this alert type is enabled.
    Sends to all configured notification_channels for the tenant.
    Returns True if at least one channel delivered successfully.
    """
    channels, preferences = await _get_tenant_notification_config(tenant_id, session)

    # Check if real-time alerts are enabled
    if not preferences.get("real_time_alerts", True):
        logger.debug("Real-time alerts disabled for tenant %s", tenant_id)
        return False

    # Check if this specific alert type is enabled
    allowed_types = preferences.get("alert_types", ["positive_reply", "meeting_booked", "pool_depleted"])
    if event_type not in allowed_types:
        logger.debug("Alert type %s not enabled for tenant %s", event_type, tenant_id)
        return False

    if not channels:
        logger.debug("No notification channels configured for tenant %s", tenant_id)
        return False

    # Format the alert message
    name = lead_data.get("name", "Unknown")
    company = lead_data.get("company", "Unknown")
    campaign_name = lead_data.get("campaign_name", "Unknown")

    message_templates = {
        "positive_reply": f"New positive reply from {name} at {company}",
        "meeting_booked": f"Meeting booked with {name} at {company}",
        "pool_depleted": f"Campaign {campaign_name} depleted lead pool",
    }

    message_text = message_templates.get(event_type, f"Alert: {event_type}")

    try:
        return await _send_to_channels(channels, message_text)
    except Exception as exc:
        logger.error("Failed to send real-time alert for tenant %s: %s", tenant_id, exc)
        return False
