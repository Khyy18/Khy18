"""Client feedback collection and analysis agent."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import LeadFeedback, Lead, Tenant
from integrations.notifications import _get_tenant_notification_config, _send_to_channels

logger = logging.getLogger(__name__)


class FeedbackCollector:
    """Collects and analyzes client feedback on lead and message quality."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], settings: Any):
        self.session_factory = session_factory
        self.settings = settings

    async def collect_feedback(
        self,
        lead_id: UUID,
        tenant_id: UUID,
        rating: int,
        comment: str | None,
        feedback_type: str,
        event_trigger: str,
    ) -> LeadFeedback:
        """Store a feedback record in the database.

        Args:
            lead_id: The lead being rated.
            tenant_id: The tenant providing feedback.
            rating: Rating from 1-5.
            comment: Optional text comment.
            feedback_type: One of 'lead_quality', 'message_quality', 'general'.
            event_trigger: One of 'meeting_booked', 'negative_reply', 'manual'.

        Returns:
            The created LeadFeedback record.
        """
        async with self.session_factory() as session:
            feedback = LeadFeedback(
                lead_id=lead_id,
                tenant_id=tenant_id,
                rating=rating,
                comment=comment,
                feedback_type=feedback_type,
                event_trigger=event_trigger,
            )
            session.add(feedback)
            await session.commit()
            await session.refresh(feedback)
            return feedback

    async def process_feedback_batch(self, tenant_id: UUID) -> dict[str, Any]:
        """Analyze recent feedback and return adjustment recommendations.

        Looks at last 30 days of feedback. Low-rated leads suggest ICP changes,
        high-rated leads suggest looking for lookalikes.

        Returns:
            Dict with recommendations based on feedback analysis.
        """
        async with self.session_factory() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)

            # Get recent feedback
            result = await session.execute(
                select(LeadFeedback).where(
                    LeadFeedback.tenant_id == tenant_id,
                    LeadFeedback.created_at >= cutoff,
                )
            )
            feedbacks = result.scalars().all()

            if not feedbacks:
                return {
                    "total_feedbacks": 0,
                    "average_rating": 0.0,
                    "recommendations": [],
                }

            total = len(feedbacks)
            avg_rating = sum(f.rating for f in feedbacks) / total

            recommendations = []

            # Analyze low-rated feedback
            low_rated = [f for f in feedbacks if f.rating <= 2]
            if len(low_rated) > total * 0.3:
                recommendations.append(
                    "High proportion of low-rated leads. Consider refining ICP criteria."
                )

            # Analyze by feedback type
            lead_quality_feedbacks = [f for f in feedbacks if f.feedback_type == "lead_quality"]
            if lead_quality_feedbacks:
                lq_avg = sum(f.rating for f in lead_quality_feedbacks) / len(lead_quality_feedbacks)
                if lq_avg < 3.0:
                    recommendations.append(
                        "Lead quality scores are below average. Review targeting parameters."
                    )

            message_quality_feedbacks = [f for f in feedbacks if f.feedback_type == "message_quality"]
            if message_quality_feedbacks:
                mq_avg = sum(f.rating for f in message_quality_feedbacks) / len(message_quality_feedbacks)
                if mq_avg < 3.0:
                    recommendations.append(
                        "Message quality scores are low. Consider A/B testing new templates."
                    )

            # High-rated leads suggest lookalikes
            high_rated = [f for f in feedbacks if f.rating >= 4]
            if len(high_rated) > total * 0.3:
                recommendations.append(
                    "Strong positive feedback on multiple leads. Look for lookalike prospects."
                )

            return {
                "total_feedbacks": total,
                "average_rating": round(avg_rating, 2),
                "recommendations": recommendations,
            }

    async def send_feedback_request(
        self,
        tenant_id: UUID,
        lead_id: UUID,
        event_trigger: str,
    ) -> bool:
        """Send a 1-click rating prompt to the client via notification channels.

        Args:
            tenant_id: The tenant to notify.
            lead_id: The lead related to the feedback request.
            event_trigger: The event that triggered the request.

        Returns:
            True if notification was sent successfully.
        """
        async with self.session_factory() as session:
            # Get lead info
            lead_result = await session.execute(
                select(Lead).where(Lead.id == lead_id)
            )
            lead = lead_result.scalar_one_or_none()
            if not lead:
                logger.warning("Lead %s not found for feedback request", lead_id)
                return False

            lead_name = f"{lead.first_name} {lead.last_name}"
            lead_company = lead.company

            # Get notification channels
            channels, preferences = await _get_tenant_notification_config(tenant_id, session)
            if not channels:
                logger.debug("No notification channels for tenant %s", tenant_id)
                return False

            message_text = (
                f"*Feedback Request*\n\n"
                f"How would you rate the quality of this lead?\n"
                f"*Lead:* {lead_name} at {lead_company}\n"
                f"*Trigger:* {event_trigger}\n\n"
                f"Reply with a rating from 1 (poor) to 5 (excellent)"
            )

            return await _send_to_channels(channels, message_text)
