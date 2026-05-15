"""Lead scoring module: scores leads based on engagement signals and ICP fit."""

import asyncio
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import (
    ChannelType,
    Event,
    EventType,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
)

logger = logging.getLogger(__name__)

# Scoring weights - shared between score_lead and predict_score
ENGAGEMENT_WEIGHTS = {
    "open": 5,
    "click": 10,
    "reply": 20,
    "positive_reply": 50,
    "linkedin_connection": 15,
    "meeting_booked": 100,
}
ENGAGEMENT_CAPS = {"open": 3, "click": 3}  # max events counted
ICP_WEIGHTS = {
    "company_size_match": 20,
    "industry_match": 15,
    "title_seniority_match": 25,
    "tech_stack_match": 10,
    "trigger_events": 15,
}
MAX_ENGAGEMENT_SCORE = (
    sum(ENGAGEMENT_WEIGHTS.values())
    + (ENGAGEMENT_WEIGHTS["open"] * (ENGAGEMENT_CAPS["open"] - 1))
    + (ENGAGEMENT_WEIGHTS["click"] * (ENGAGEMENT_CAPS["click"] - 1))
)
MAX_ICP_SCORE = sum(ICP_WEIGHTS.values())
MAX_TOTAL_SCORE = MAX_ENGAGEMENT_SCORE + MAX_ICP_SCORE


class LeadScorer:
    """Scores leads based on engagement signals and ICP fit."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def score_lead(self, lead_id: UUID) -> float:
        """Calculate and save total score for a lead.

        Engagement scoring:
        - Email opened (Event with event_type=open): +5 per event (capped at 3)
        - Email clicked (event_type=click): +10 per event (capped at 3)
        - Email replied (event_type=reply or lead status=replied): +20
        - Positive reply (enrichment_data.positive_reply): +50
        - LinkedIn connection accepted (Message with channel=linkedin,
          meta containing 'linkedin_connect_task', status=sent): +15
        - Meeting booked (lead status=booked): +100

        ICP fit scoring (from lead.enrichment_data):
        - company_size_match == True: +20
        - industry_match == True: +15
        - title_seniority_match == True: +25
        - tech_stack_match == True: +10
        - trigger_events not empty: +15

        Total = engagement_score + icp_fit_score
        Save to lead.score and return.
        """
        async with self._session_factory() as session:
            # Load lead
            result = await session.execute(select(Lead).where(Lead.id == lead_id))
            lead = result.scalar_one_or_none()
            if lead is None:
                raise ValueError(f"Lead {lead_id} not found")

            engagement_score = await self._calculate_engagement(session, lead)
            icp_fit_score = self._calculate_icp_fit(lead)

            total = engagement_score + icp_fit_score
            lead.score = total
            await session.commit()
            return total

    async def _calculate_engagement(self, session: AsyncSession, lead: Lead) -> float:
        """Calculate engagement score from events and lead status."""
        score = 0.0

        # Get all message IDs for this lead
        msg_result = await session.execute(
            select(Message.id).where(Message.lead_id == lead.id)
        )
        message_ids = [row[0] for row in msg_result.all()]

        if message_ids:
            # Count open events (capped at 3)
            open_count_result = await session.execute(
                select(func.count())
                .select_from(Event)
                .where(
                    Event.message_id.in_(message_ids),
                    Event.event_type == EventType.open,
                )
            )
            open_count = min(open_count_result.scalar() or 0, 3)
            score += open_count * 5

            # Count click events (capped at 3)
            click_count_result = await session.execute(
                select(func.count())
                .select_from(Event)
                .where(
                    Event.message_id.in_(message_ids),
                    Event.event_type == EventType.click,
                )
            )
            click_count = min(click_count_result.scalar() or 0, 3)
            score += click_count * 10

            # Check for reply events
            reply_count_result = await session.execute(
                select(func.count())
                .select_from(Event)
                .where(
                    Event.message_id.in_(message_ids),
                    Event.event_type == EventType.reply,
                )
            )
            reply_count = reply_count_result.scalar() or 0
            if reply_count > 0 or lead.status == LeadStatus.replied:
                score += 20

            # Check for LinkedIn connection accepted
            linkedin_result = await session.execute(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.lead_id == lead.id,
                    Message.channel == ChannelType.linkedin,
                    Message.status.in_([MessageStatus.sent, MessageStatus.draft]),
                )
            )
            linkedin_count = linkedin_result.scalar() or 0
            if linkedin_count > 0:
                score += 15

        # Reply status without events
        if not message_ids and lead.status == LeadStatus.replied:
            score += 20

        # Positive reply from enrichment_data
        enrichment = lead.enrichment_data or {}
        if enrichment.get("positive_reply"):
            score += 50

        # Meeting booked
        if lead.status == LeadStatus.booked:
            score += 100

        return score

    @staticmethod
    def _calculate_icp_fit(lead: Lead) -> float:
        """Calculate ICP fit score from lead enrichment data."""
        score = 0.0
        enrichment = lead.enrichment_data or {}

        if enrichment.get("company_size_match") is True:
            score += 20
        if enrichment.get("industry_match") is True:
            score += 15
        if enrichment.get("title_seniority_match") is True:
            score += 25
        if enrichment.get("tech_stack_match") is True:
            score += 10
        if enrichment.get("trigger_events"):
            score += 15

        return score

    async def bulk_rescore(self, campaign_id: UUID) -> int:
        """Recalculate scores for all leads in a campaign. Returns count of leads rescored."""
        async with self._session_factory() as session:
            # Get all lead IDs in campaign via messages
            lead_ids_result = await session.execute(
                select(Message.lead_id)
                .where(Message.campaign_id == campaign_id)
                .distinct()
            )
            lead_ids = [row[0] for row in lead_ids_result.all()]

        count = 0
        for lid in lead_ids:
            await self.score_lead(lid)
            count += 1

        return count

    async def get_hot_leads(self, tenant_id: UUID, threshold: float = 80.0) -> list:
        """Get leads with score > threshold, sorted by score desc."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Lead)
                .where(
                    Lead.tenant_id == tenant_id,
                    Lead.score > threshold,
                )
                .order_by(Lead.score.desc())
            )
            return list(result.scalars().all())

    @staticmethod
    def predict_score(lead_data: dict, engagement_data: dict) -> float:
        """Placeholder for future ML model integration.

        For now: returns weighted sum of engagement + ICP fit as percentage (0-100).
        """
        engagement_score = 0.0

        opens = min(engagement_data.get("opens", 0), ENGAGEMENT_CAPS["open"])
        clicks = min(engagement_data.get("clicks", 0), ENGAGEMENT_CAPS["click"])
        engagement_score += opens * ENGAGEMENT_WEIGHTS["open"]
        engagement_score += clicks * ENGAGEMENT_WEIGHTS["click"]
        if engagement_data.get("replied"):
            engagement_score += ENGAGEMENT_WEIGHTS["reply"]
        if engagement_data.get("positive_reply"):
            engagement_score += ENGAGEMENT_WEIGHTS["positive_reply"]
        if engagement_data.get("linkedin_connected"):
            engagement_score += ENGAGEMENT_WEIGHTS["linkedin_connection"]
        if engagement_data.get("booked"):
            engagement_score += ENGAGEMENT_WEIGHTS["meeting_booked"]

        icp_score = 0.0
        if lead_data.get("company_size_match"):
            icp_score += ICP_WEIGHTS["company_size_match"]
        if lead_data.get("industry_match"):
            icp_score += ICP_WEIGHTS["industry_match"]
        if lead_data.get("title_seniority_match"):
            icp_score += ICP_WEIGHTS["title_seniority_match"]
        if lead_data.get("tech_stack_match"):
            icp_score += ICP_WEIGHTS["tech_stack_match"]
        if lead_data.get("trigger_events"):
            icp_score += ICP_WEIGHTS["trigger_events"]

        total = engagement_score + icp_score
        return min(round((total / MAX_TOTAL_SCORE) * 100, 1), 100.0)


async def trigger_score_update(lead_id: UUID, session_factory) -> None:
    """Fire-and-forget score update. Logs errors but does not raise."""
    try:
        scorer = LeadScorer(session_factory)
        await scorer.score_lead(lead_id)
    except Exception as exc:
        logger.error("Failed to update score for lead %s: %s", lead_id, str(exc))
