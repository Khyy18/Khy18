"""WarmupNetwork - Cross-tenant domain warming via network of participating domains."""

from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import Tenant

logger = logging.getLogger(__name__)

# Warmup email templates - varied realistic business content (30+ templates)
_NETWORK_TEMPLATES: list[dict[str, str]] = [
    {"subject": "Quick question about your availability", "body": "Hi there,\n\nI wanted to check in and see if you have some time this week to discuss the quarterly planning. Let me know what works best for your schedule.\n\nBest regards"},
    {"subject": "Re: Meeting notes from yesterday", "body": "Thanks for sending those over. I reviewed the notes and everything looks good on my end. Let me know if there are any action items you need me to follow up on.\n\nCheers"},
    {"subject": "Document review request", "body": "Hi,\n\nCould you take a look at the updated proposal when you get a chance? I made the changes we discussed in the last meeting. No rush, but would be great to have your feedback by end of week.\n\nThanks"},
    {"subject": "Team lunch next week", "body": "Hey team,\n\nJust wanted to float the idea of doing a team lunch next Wednesday or Thursday. Any preferences on the day or restaurant? I was thinking somewhere downtown.\n\nLet me know!"},
    {"subject": "Updated schedule for Q2", "body": "Hi everyone,\n\nAttached is the updated schedule for Q2 projects. Please review your assigned deadlines and let me know if there are any conflicts with your current workload.\n\nBest"},
    {"subject": "Re: Budget approval", "body": "Great news - the budget got approved this morning. We can go ahead and proceed with the vendor selection process. I will set up a call with the top two candidates this week.\n\nTalk soon"},
    {"subject": "Conference registration reminder", "body": "Hi,\n\nJust a friendly reminder that the early bird registration for the industry conference closes on Friday. If you are planning to attend, now is a good time to sign up.\n\nRegards"},
    {"subject": "Feedback on the presentation", "body": "Hi,\n\nReally enjoyed your presentation this morning. The data on customer retention was particularly insightful. Would love to chat more about how we can apply those findings to our team.\n\nGreat job!"},
    {"subject": "Office supplies order", "body": "Hi,\n\nI am putting in the monthly office supplies order. If you need anything specific (notebooks, pens, etc.), please reply by end of day tomorrow and I will add it to the list.\n\nThanks"},
    {"subject": "New project kickoff", "body": "Hi team,\n\nExcited to announce we are kicking off the new client project next Monday. I will send out a calendar invite for the kickoff meeting shortly. Please come prepared with any initial questions.\n\nLooking forward to it"},
    {"subject": "Parking situation update", "body": "Hi all,\n\nQuick update: the west parking lot will be under maintenance starting next week. Please use the east lot or street parking for the next two weeks. Sorry for the inconvenience.\n\nThanks for understanding"},
    {"subject": "Happy Friday!", "body": "Hey,\n\nHope you had a productive week! Just wanted to say great work on hitting the milestone yesterday. Enjoy the weekend and we will regroup on Monday.\n\nHave a good one"},
    {"subject": "Client feedback summary", "body": "Hi,\n\nI compiled the feedback from last week's client demos. Overall reception was very positive. I have attached the summary with key takeaways and suggested next steps.\n\nLet me know your thoughts"},
    {"subject": "Training session this Thursday", "body": "Hi team,\n\nReminder that the new tool training session is this Thursday at 2pm. Please bring your laptops so we can do the hands-on portion together. Calendar invite incoming.\n\nSee you there"},
    {"subject": "Vendor contract renewal", "body": "Hi,\n\nOur annual contract with the analytics vendor is up for renewal next month. I have been reviewing alternatives and would like to discuss before we commit. Can we sync this week?\n\nThanks"},
    {"subject": "Re: Product roadmap review", "body": "Thanks for sharing the updated roadmap. The timeline for Phase 2 looks tight but doable. I have a few suggestions on prioritization that I think could help. Happy to walk through them.\n\nBest"},
    {"subject": "Holiday party planning", "body": "Hey everyone,\n\nWe are starting to plan the end-of-year holiday party. If anyone has venue suggestions or theme ideas, please reply to this thread. Budget is similar to last year.\n\nExcited to celebrate together!"},
    {"subject": "Weekly standup notes", "body": "Hi team,\n\nHere are the highlights from this week's standups. We made great progress on the integration work and the beta testers reported fewer issues. Full notes attached.\n\nKeep up the great work"},
    {"subject": "New hire introduction", "body": "Hi all,\n\nWanted to let everyone know that Sarah will be joining our team next Monday as a senior analyst. She comes from a great background in data science. Please make her feel welcome!\n\nExcited to have her on board"},
    {"subject": "IT maintenance window", "body": "Hi everyone,\n\nIT will be performing server maintenance this Saturday from 10pm to 2am. Email and internal tools may be briefly unavailable during this time. Please plan accordingly.\n\nThanks for your patience"},
    {"subject": "Quarterly review prep", "body": "Hi,\n\nThe quarterly review is in two weeks. Please start preparing your team's accomplishments and metrics. I have shared the slide template in the shared drive. Let me know if you need any data from me.\n\nThanks"},
    {"subject": "Lunch and learn tomorrow", "body": "Hey team,\n\nReminder about tomorrow's lunch and learn session on cloud architecture best practices. Pizza will be provided. Conference room B at noon.\n\nHope to see you there!"},
    {"subject": "Re: Expense report question", "body": "Hi,\n\nYes, the conference travel expenses should be submitted under the events category. I have approved your previous submission as well. Let me know if you have any other questions.\n\nBest"},
    {"subject": "Team building activity next month", "body": "Hi everyone,\n\nWe are planning a team building activity for the first Friday of next month. Options are: escape room, cooking class, or bowling. Please vote by replying with your preference.\n\nLooking forward to it!"},
    {"subject": "Process improvement suggestion", "body": "Hi,\n\nI have been thinking about how we can streamline our review process. What if we tried async reviews with a 24-hour turnaround SLA? I think it could save us two meetings per week.\n\nThoughts?"},
    {"subject": "Welcome back from vacation!", "body": "Hey,\n\nHope you had a fantastic trip! Not much has changed while you were away. I have prepared a brief catch-up doc with the key decisions and updates from last week. Take your time settling back in.\n\nWelcome back!"},
    {"subject": "Re: Partnership proposal", "body": "Thanks for forwarding this. The partnership terms look reasonable. I think it aligns well with our Q3 goals. Let me review the financial details and we can discuss in our next sync.\n\nAppreciate you flagging this"},
    {"subject": "Software license renewal", "body": "Hi,\n\nOur design tool licenses expire at the end of the month. Do we want to renew at the current tier or upgrade? I noticed we are consistently hitting the user limit. Let me know your thoughts.\n\nThanks"},
    {"subject": "Office temperature feedback", "body": "Hi all,\n\nWe have received mixed feedback about the office temperature. If you are finding it too cold or too warm, please fill out the quick survey I sent earlier today so facilities can adjust.\n\nThank you!"},
    {"subject": "Congratulations on the launch!", "body": "Hey team,\n\nHuge congratulations on yesterday's product launch! The numbers are looking great and client feedback has been overwhelmingly positive. You all deserve to celebrate this win.\n\nAmazing work!"},
    {"subject": "Re: Interview schedule", "body": "Hi,\n\nI have confirmed the interview panel for next Tuesday. You are scheduled for the 2pm slot for a 45-minute technical discussion. I will send the candidate's resume and portfolio ahead of time.\n\nThanks for helping out"},
    {"subject": "Monthly newsletter draft", "body": "Hi,\n\nI have put together the first draft of this month's customer newsletter. Could you review the product updates section and make sure the feature descriptions are accurate? No rush, by Thursday works.\n\nThanks!"},
]


class WarmupNetwork:
    """Manages cross-tenant domain warming by exchanging warmup emails between network domains."""

    def __init__(self, redis_url: str, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._redis_url = redis_url
        self._session_factory = session_factory
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def get_network_domains(self) -> list[str]:
        """Query all tenant domains from the database.

        Returns:
            List of domain strings from all tenants in the system.
        """
        async with self._session_factory() as session:
            result = await session.execute(select(Tenant.domain))
            domains = [row[0] for row in result.all()]
        return domains

    def generate_warmup_pair(self, sender_domain: str, network_domains: list[str] | None = None) -> tuple[str, str, str, str]:
        """Pick a random receiver domain from network (not self) and generate email content.

        Args:
            sender_domain: The sending domain.
            network_domains: Optional list of available domains. If None, must be provided externally.

        Returns:
            Tuple of (sender_email, receiver_email, subject, body).

        Raises:
            ValueError: If no other domains are available in the network.
        """
        if network_domains is None:
            network_domains = []

        # Filter out the sender's own domain
        available = [d for d in network_domains if d != sender_domain]
        if not available:
            raise ValueError(f"No other domains available in network for {sender_domain}")

        receiver_domain = random.choice(available)

        # Generate realistic email addresses
        sender_prefixes = ["info", "hello", "team", "support", "contact", "admin", "sales", "marketing"]
        receiver_prefixes = ["info", "hello", "team", "support", "contact", "admin", "office", "hr"]

        sender_email = f"{random.choice(sender_prefixes)}@{sender_domain}"
        receiver_email = f"{random.choice(receiver_prefixes)}@{receiver_domain}"

        # Pick a random template
        template = random.choice(_NETWORK_TEMPLATES)
        subject = template["subject"]
        body = template["body"]

        return sender_email, receiver_email, subject, body

    def schedule_network_warmup(self, domain: str, daily_quota: int) -> list[dict[str, Any]]:
        """Create a schedule spread throughout the day with random delays.

        Args:
            domain: The domain to schedule warmup for.
            daily_quota: Number of warmup emails to schedule for the day.

        Returns:
            List of dicts with scheduled send times and metadata.
        """
        if daily_quota <= 0:
            return []

        schedule: list[dict[str, Any]] = []
        # Spread sends across working hours (8am to 6pm = 600 minutes)
        work_start_minutes = 8 * 60  # 8:00 AM
        work_end_minutes = 18 * 60  # 6:00 PM
        available_minutes = work_end_minutes - work_start_minutes

        # Minimum gap between sends: 5 minutes
        min_gap = 5
        # Random delay added: 5-60 minutes between sends
        current_minute = work_start_minutes + random.randint(0, 30)

        for i in range(daily_quota):
            if current_minute >= work_end_minutes:
                current_minute = work_start_minutes + random.randint(0, 60)

            hour = current_minute // 60
            minute = current_minute % 60

            schedule.append({
                "domain": domain,
                "send_at_hour": hour,
                "send_at_minute": minute,
                "sequence_index": i,
                "message_id": str(uuid.uuid4()),
            })

            # Add random delay between sends (5-60 min)
            gap = random.randint(min_gap, 60)
            current_minute += gap

        return schedule

    async def simulate_engagement(self, message_id: str) -> None:
        """Record simulated open/reply for a warmup message.

        Marks the message as opened after a random delay simulation.
        Stores engagement data in Redis.

        Args:
            message_id: The message ID to simulate engagement for.
        """
        redis = await self._get_redis()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Record open event (TTL: 48 hours)
        engagement_key = f"warmup_network:engagement:{message_id}"
        now = datetime.now(timezone.utc).isoformat()
        await redis.hset(engagement_key, mapping={
            "opened": "true",
            "opened_at": now,
            "message_id": message_id,
        })
        await redis.expire(engagement_key, 172800)  # 48 hours

        # Update domain sends counter from the message metadata
        msg_key = f"warmup_network:message:{message_id}"
        domain = await redis.hget(msg_key, "sender_domain")
        if domain:
            opens_key = f"warmup_network:{domain}:opens:{today}"
            await redis.incr(opens_key)
            await redis.expire(opens_key, 172800)  # 48 hours

    async def get_network_health(self, domain: str) -> dict[str, Any]:
        """Return stats for a domain in the warmup network.

        Args:
            domain: The domain to check health for.

        Returns:
            Dict with total_sends, opens, replies, and health_score (0-100).
        """
        redis = await self._get_redis()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        sends_key = f"warmup_network:{domain}:sends:{today}"
        opens_key = f"warmup_network:{domain}:opens:{today}"
        replies_key = f"warmup_network:{domain}:replies:{today}"

        total_sends = int(await redis.get(sends_key) or 0)
        opens = int(await redis.get(opens_key) or 0)
        replies = int(await redis.get(replies_key) or 0)

        # Health score: weighted average of open rate and reply rate
        if total_sends > 0:
            open_rate = opens / total_sends
            reply_rate = replies / total_sends
            # Health score formula: 60% open rate + 40% reply rate, normalized to 0-100
            health_score = int(min((open_rate * 0.6 + reply_rate * 0.4) * 100, 100))
        else:
            health_score = 0

        return {
            "domain": domain,
            "total_sends": total_sends,
            "opens": opens,
            "replies": replies,
            "health_score": health_score,
        }

    async def record_send(self, domain: str, message_id: str, sender_email: str, receiver_email: str) -> None:
        """Record a warmup network send in Redis.

        Args:
            domain: Sender domain.
            message_id: Unique message identifier.
            sender_email: Sender email address.
            receiver_email: Receiver email address.
        """
        redis = await self._get_redis()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Track daily sends with date-partitioned key and TTL
        sends_key = f"warmup_network:{domain}:sends:{today}"
        await redis.incr(sends_key)
        await redis.expire(sends_key, 172800)  # 48 hours

        # Store message metadata with TTL
        msg_key = f"warmup_network:message:{message_id}"
        await redis.hset(msg_key, mapping={
            "sender_domain": domain,
            "sender_email": sender_email,
            "receiver_email": receiver_email,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
        await redis.expire(msg_key, 172800)  # 48 hours

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis:
            await self._redis.close()
