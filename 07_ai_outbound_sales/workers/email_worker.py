"""Email worker tasks for ARQ queue."""

from __future__ import annotations

import json
import logging
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)


async def send_email_task(
    ctx: dict[str, Any],
    to: str,
    subject: str,
    html_body: str,
    message_id: str,
    tracking_pixel_url: str | None = None,
    tracked_links: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Send an email via AsyncEmailSender with domain rotation."""
    from channels.email.sender import AsyncEmailSender

    smtp_accounts = json.loads(settings.smtp_domains)
    sender = AsyncEmailSender(
        smtp_accounts=smtp_accounts,
        redis_url=settings.redis_url,
    )
    try:
        result = await sender.send_email(
            to=to,
            subject=subject,
            html_body=html_body,
            message_id=message_id,
            tracking_pixel_url=tracking_pixel_url,
            tracked_links=tracked_links,
        )
        return result
    finally:
        await sender.close()


async def send_warmup_task(
    ctx: dict[str, Any],
    domain: str,
    to: str,
    subject: str,
    html_body: str,
    message_id: str,
) -> dict[str, Any]:
    """Send a warmup email via a specific domain."""
    from channels.email.sender import AsyncEmailSender

    smtp_accounts = json.loads(settings.smtp_domains)
    sender = AsyncEmailSender(
        smtp_accounts=smtp_accounts,
        redis_url=settings.redis_url,
    )
    try:
        result = await sender.send_email_from_domain(
            domain=domain,
            to=to,
            subject=subject,
            html_body=html_body,
            message_id=message_id,
        )
        return result
    finally:
        await sender.close()
