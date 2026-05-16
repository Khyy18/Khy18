"""Smart Sequence Optimizer - determines next best action for lead engagement."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import Settings
from core.llm import LLMClient
from core.models import (
    Call,
    CallOutcome,
    CallStatus,
    Event,
    EventType,
    Lead,
    LeadInteraction,
    Message,
    MessageDirection,
    MessageStatus,
    ChannelType,
)

logger = logging.getLogger(__name__)


class NextAction(BaseModel):
    """Recommended next action for a lead."""

    channel: str
    delay_hours: int
    reasoning: str
    confidence: float


class SequenceOptimizerAgent:
    """Determines the optimal next action for lead engagement using rules and AI."""

    def __init__(
        self,
        llm_client: LLMClient,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._llm = llm_client
        self._session_factory = session_factory
        self._settings = settings

    async def get_next_action(self, lead_id: UUID) -> NextAction:
        """Determine the next best action for engaging a lead.

        Uses a rules engine to analyze past interactions and determine
        the optimal channel, timing, and approach.

        Args:
            lead_id: UUID of the lead.

        Returns:
            NextAction with channel, delay, reasoning, and confidence.
        """
        async with self._session_factory() as session:
            # Load lead
            lead_result = await session.execute(
                select(Lead).where(Lead.id == lead_id)
            )
            lead = lead_result.scalar_one_or_none()
            if lead is None:
                return NextAction(
                    channel="email",
                    delay_hours=0,
                    reasoning="Lead not found, defaulting to email",
                    confidence=0.3,
                )

            # Load recent interactions
            interactions = await self._load_recent_interactions(lead_id, session)

            # Load recent calls
            calls = await self._load_recent_calls(lead_id, session)

            # Load recent messages/events
            messages_data = await self._load_recent_messages(lead_id, session)

            # Apply rules engine
            return self._apply_rules(interactions, calls, messages_data)

    async def calculate_engagement_score(self, lead_id: UUID) -> float:
        """Calculate real-time engagement score based on all interactions.

        Score is 0.0-1.0 based on recency and quality of interactions.

        Args:
            lead_id: UUID of the lead.

        Returns:
            Engagement score between 0.0 and 1.0.
        """
        async with self._session_factory() as session:
            now = datetime.now(timezone.utc)
            score = 0.0

            # Count interactions in last 7 days
            recent_interactions = await session.execute(
                select(func.count())
                .select_from(LeadInteraction)
                .where(
                    LeadInteraction.lead_id == lead_id,
                    LeadInteraction.created_at >= now - timedelta(days=7),
                )
            )
            interaction_count = recent_interactions.scalar() or 0
            score += min(interaction_count * 0.1, 0.3)

            # Check for email opens/clicks
            msg_result = await session.execute(
                select(Message.id).where(Message.lead_id == lead_id)
            )
            message_ids = [row[0] for row in msg_result.all()]

            if message_ids:
                open_count = await session.execute(
                    select(func.count())
                    .select_from(Event)
                    .where(
                        Event.message_id.in_(message_ids),
                        Event.event_type == EventType.open,
                    )
                )
                opens = open_count.scalar() or 0
                score += min(opens * 0.1, 0.2)

                click_count = await session.execute(
                    select(func.count())
                    .select_from(Event)
                    .where(
                        Event.message_id.in_(message_ids),
                        Event.event_type == EventType.click,
                    )
                )
                clicks = click_count.scalar() or 0
                score += min(clicks * 0.15, 0.3)

            # Check for answered calls
            answered_calls = await session.execute(
                select(func.count())
                .select_from(Call)
                .where(
                    Call.lead_id == lead_id,
                    Call.status.in_([CallStatus.answered, CallStatus.completed]),
                )
            )
            answered = answered_calls.scalar() or 0
            score += min(answered * 0.2, 0.2)

            return min(score, 1.0)

    async def _load_recent_interactions(
        self, lead_id: UUID, session: AsyncSession
    ) -> list[dict[str, Any]]:
        """Load recent interactions for rules engine."""
        result = await session.execute(
            select(LeadInteraction)
            .where(LeadInteraction.lead_id == lead_id)
            .order_by(LeadInteraction.created_at.desc())
            .limit(10)
        )
        interactions = result.scalars().all()
        return [
            {
                "type": i.interaction_type,
                "channel": i.channel,
                "created_at": i.created_at,
                "context": i.context_json or {},
            }
            for i in interactions
        ]

    async def _load_recent_calls(
        self, lead_id: UUID, session: AsyncSession
    ) -> list[dict[str, Any]]:
        """Load recent calls for rules engine."""
        result = await session.execute(
            select(Call)
            .where(Call.lead_id == lead_id)
            .order_by(Call.created_at.desc())
            .limit(5)
        )
        calls = result.scalars().all()
        return [
            {
                "status": c.status.value if c.status else None,
                "outcome": c.outcome.value if c.outcome else None,
                "created_at": c.created_at,
                "started_at": c.started_at,
            }
            for c in calls
        ]

    async def _load_recent_messages(
        self, lead_id: UUID, session: AsyncSession
    ) -> dict[str, Any]:
        """Load recent message data including events."""
        result = await session.execute(
            select(Message)
            .where(Message.lead_id == lead_id)
            .order_by(Message.sent_at.desc())
            .limit(10)
        )
        messages = result.scalars().all()

        email_opened = False
        email_replied = False
        linkedin_sent = False
        linkedin_viewed = False
        last_email_sent_at: datetime | None = None

        for msg in messages:
            if msg.channel == ChannelType.email and msg.direction == MessageDirection.outbound:
                if last_email_sent_at is None:
                    last_email_sent_at = msg.sent_at
                if msg.status == MessageStatus.opened:
                    email_opened = True
                if msg.status == MessageStatus.replied:
                    email_replied = True
            if msg.channel == ChannelType.linkedin:
                if msg.direction == MessageDirection.outbound:
                    linkedin_sent = True
                meta = msg.meta or {}
                if meta.get("viewed"):
                    linkedin_viewed = True

        return {
            "email_opened": email_opened,
            "email_replied": email_replied,
            "linkedin_sent": linkedin_sent,
            "linkedin_viewed": linkedin_viewed,
            "last_email_sent_at": last_email_sent_at,
        }

    def _apply_rules(
        self,
        interactions: list[dict[str, Any]],
        calls: list[dict[str, Any]],
        messages_data: dict[str, Any],
    ) -> NextAction:
        """Apply rules engine logic to determine next action.

        Rules:
        1. Email opened but no reply within 24h -> recommend call in 2h
        2. Call no-answer -> recommend LinkedIn message next day
        3. LinkedIn viewed but no response -> recommend email follow-up in 1 day
        4. Multiple no-answers -> recommend different time of day
        5. Default: email with standard delay
        """
        now = datetime.now(timezone.utc)

        # Rule 1: Email opened but no reply -> call
        if messages_data.get("email_opened") and not messages_data.get("email_replied"):
            last_sent = messages_data.get("last_email_sent_at")
            if last_sent:
                # Ensure timezone-aware comparison
                if last_sent.tzinfo is None:
                    last_sent = last_sent.replace(tzinfo=timezone.utc)
                if (now - last_sent) > timedelta(hours=24):
                    return NextAction(
                        channel="voice",
                        delay_hours=2,
                        reasoning="Email was opened but no reply after 24h - prospect showed interest, call to follow up",
                        confidence=0.8,
                    )

        # Rule 2: Call no-answer -> LinkedIn next day
        no_answer_calls = [
            c for c in calls
            if c.get("status") == "no_answer" or c.get("outcome") == "no_answer"
        ]
        if no_answer_calls:
            last_no_answer = no_answer_calls[0]
            # Rule 4: Multiple no-answers -> different time of day
            if len(no_answer_calls) >= 2:
                return NextAction(
                    channel="voice",
                    delay_hours=28,
                    reasoning="Multiple no-answers - trying different time of day",
                    confidence=0.6,
                )
            return NextAction(
                channel="linkedin",
                delay_hours=24,
                reasoning="Call went unanswered - trying LinkedIn as alternative channel",
                confidence=0.7,
            )

        # Rule 3: LinkedIn viewed but no response -> email follow-up
        if messages_data.get("linkedin_viewed") and messages_data.get("linkedin_sent"):
            return NextAction(
                channel="email",
                delay_hours=24,
                reasoning="LinkedIn message was viewed but no response - following up via email",
                confidence=0.7,
            )

        # Default: start with email
        return NextAction(
            channel="email",
            delay_hours=0,
            reasoning="No prior engagement signals - starting with email outreach",
            confidence=0.5,
        )
