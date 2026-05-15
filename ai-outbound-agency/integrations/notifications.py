"""Notification integrations - Slack and Telegram for human-in-the-loop alerts."""

from __future__ import annotations

import logging
from typing import Any

import httpx

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
