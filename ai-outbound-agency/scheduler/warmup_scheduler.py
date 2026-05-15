"""Warmup Scheduler - sends warmup emails to build domain reputation."""

from __future__ import annotations

import logging
import random
import uuid
from typing import Any

import redis.asyncio as aioredis

from channels.email.sender import AsyncEmailSender
from channels.email.warmup import DomainWarmupManager

logger = logging.getLogger(__name__)

# Warmup email templates - professional business content with varied subjects
_WARMUP_TEMPLATES: list[dict[str, str]] = [
    {
        "subject": "Quick question about your availability",
        "body": (
            "Hi there,\n\n"
            "I wanted to check in and see if you have some time this week "
            "to discuss the quarterly planning. Let me know what works best "
            "for your schedule.\n\n"
            "Best regards"
        ),
    },
    {
        "subject": "Re: Meeting notes from yesterday",
        "body": (
            "Thanks for sending those over. I reviewed the notes and "
            "everything looks good on my end. Let me know if there are "
            "any action items you need me to follow up on.\n\n"
            "Cheers"
        ),
    },
    {
        "subject": "Document review request",
        "body": (
            "Hi,\n\n"
            "Could you take a look at the updated proposal when you get "
            "a chance? I made the changes we discussed in the last meeting. "
            "No rush, but would be great to have your feedback by end of week.\n\n"
            "Thanks"
        ),
    },
    {
        "subject": "Team lunch next week",
        "body": (
            "Hey team,\n\n"
            "Just wanted to float the idea of doing a team lunch next "
            "Wednesday or Thursday. Any preferences on the day or restaurant? "
            "I was thinking somewhere downtown.\n\n"
            "Let me know!"
        ),
    },
    {
        "subject": "Updated schedule for Q2",
        "body": (
            "Hi everyone,\n\n"
            "Attached is the updated schedule for Q2 projects. Please review "
            "your assigned deadlines and let me know if there are any conflicts "
            "with your current workload.\n\n"
            "Best"
        ),
    },
    {
        "subject": "Re: Budget approval",
        "body": (
            "Great news - the budget got approved this morning. We can go "
            "ahead and proceed with the vendor selection process. I will set "
            "up a call with the top two candidates this week.\n\n"
            "Talk soon"
        ),
    },
    {
        "subject": "Conference registration reminder",
        "body": (
            "Hi,\n\n"
            "Just a friendly reminder that the early bird registration for "
            "the industry conference closes on Friday. If you are planning "
            "to attend, now is a good time to sign up.\n\n"
            "Regards"
        ),
    },
    {
        "subject": "Feedback on the presentation",
        "body": (
            "Hi,\n\n"
            "Really enjoyed your presentation this morning. The data on "
            "customer retention was particularly insightful. Would love to "
            "chat more about how we can apply those findings to our team.\n\n"
            "Great job!"
        ),
    },
    {
        "subject": "Office supplies order",
        "body": (
            "Hi,\n\n"
            "I am putting in the monthly office supplies order. If you need "
            "anything specific (notebooks, pens, etc.), please reply by end "
            "of day tomorrow and I will add it to the list.\n\n"
            "Thanks"
        ),
    },
    {
        "subject": "New project kickoff",
        "body": (
            "Hi team,\n\n"
            "Excited to announce we are kicking off the new client project "
            "next Monday. I will send out a calendar invite for the kickoff "
            "meeting shortly. Please come prepared with any initial questions.\n\n"
            "Looking forward to it"
        ),
    },
    {
        "subject": "Parking situation update",
        "body": (
            "Hi all,\n\n"
            "Quick update: the west parking lot will be under maintenance "
            "starting next week. Please use the east lot or street parking "
            "for the next two weeks. Sorry for the inconvenience.\n\n"
            "Thanks for understanding"
        ),
    },
    {
        "subject": "Happy Friday!",
        "body": (
            "Hey,\n\n"
            "Hope you had a productive week! Just wanted to say great work "
            "on hitting the milestone yesterday. Enjoy the weekend and we will "
            "regroup on Monday.\n\n"
            "Have a good one"
        ),
    },
]


class WarmupScheduler:
    """Sends warmup emails between owned domains to build sending reputation."""

    def __init__(
        self,
        warmup_manager: DomainWarmupManager,
        email_sender: AsyncEmailSender,
        redis_url: str,
        seed_addresses: list[str] | None = None,
    ) -> None:
        self._warmup_manager = warmup_manager
        self._email_sender = email_sender
        self._redis_url = redis_url
        self._seed_addresses = seed_addresses or []
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def run_warmup_tick(self) -> None:
        """Execute one tick of the warmup scheduler.

        For each domain that is not yet fully warmed up, sends warmup
        emails up to the remaining daily limit.
        """
        logger.info("Warmup scheduler tick started")

        try:
            warmup_status = await self._warmup_manager.get_warmup_status()
        except Exception as exc:
            logger.error("Failed to get warmup status: %s", exc, exc_info=True)
            return

        if not warmup_status:
            logger.info("No domains being warmed up")
            return

        for domain, status in warmup_status.items():
            try:
                await self._process_domain(domain, status)
            except Exception as exc:
                logger.error(
                    "Error processing warmup for domain %s: %s",
                    domain,
                    exc,
                    exc_info=True,
                )

        logger.info("Warmup scheduler tick completed")

    async def _process_domain(
        self, domain: str, status: dict[str, Any]
    ) -> None:
        """Process warmup sends for a single domain."""
        if status.get("is_warmed_up"):
            logger.debug("Domain %s is fully warmed up, skipping", domain)
            return

        daily_limit = status.get("daily_limit", 5)
        sends_today = status.get("sends_today", 0)
        remaining = daily_limit - sends_today

        if remaining <= 0:
            logger.debug(
                "Domain %s has reached daily warmup limit (%d/%d)",
                domain,
                sends_today,
                daily_limit,
            )
            return

        logger.info(
            "Domain %s: sending %d warmup emails (%d/%d sent today)",
            domain,
            remaining,
            sends_today,
            daily_limit,
        )

        for _ in range(remaining):
            try:
                await self._send_warmup_email(domain)
            except Exception as exc:
                logger.error(
                    "Failed to send warmup email for %s: %s",
                    domain,
                    exc,
                    exc_info=True,
                )
                break

    async def _send_warmup_email(self, domain: str) -> None:
        """Send a single warmup email for a domain."""
        # Pick a random recipient from seed addresses
        if not self._seed_addresses:
            logger.warning(
                "No seed addresses configured for warmup, skipping domain %s",
                domain,
            )
            return

        recipient = random.choice(self._seed_addresses)

        # Pick a random template
        template = random.choice(_WARMUP_TEMPLATES)
        subject = template["subject"]
        body = template["body"]

        # Add slight variation to avoid being flagged as identical content
        message_id = str(uuid.uuid4())

        result = await self._email_sender.send_email_from_domain(
            domain=domain,
            to=recipient,
            subject=subject,
            html_body=f"<p>{body}</p>",
            message_id=message_id,
            tracking_pixel_url=None,
            tracked_links=None,
        )

        if result.get("success"):
            await self._warmup_manager.record_warmup_send(domain)
            logger.debug(
                "Warmup email sent from %s to %s (subject: %s)",
                domain,
                recipient,
                subject,
            )
        else:
            logger.warning(
                "Warmup email send failed for domain %s to %s",
                domain,
                recipient,
            )

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
