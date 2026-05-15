"""Sequence Runner - campaign execution engine that sends outreach emails on schedule."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from agents.copywriter import CopywriterAgent
from channels.email.sender import AsyncEmailSender
from channels.email.tracker import EmailTracker
from core.models import (
    ABTest,
    ABTestStatus,
    Campaign,
    CampaignStatus,
    ChannelType,
    Lead,
    LeadStatus,
    Message,
    MessageDirection,
    MessageStatus,
    Sequence,
)

logger = logging.getLogger(__name__)

# Lead statuses that should be skipped during sequence execution
_SKIP_STATUSES = {LeadStatus.replied, LeadStatus.lost, LeadStatus.booked}


class SequenceRunner:
    """Executes campaign sequences by sending emails to leads on schedule."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis_url: str,
        email_sender: AsyncEmailSender,
        copywriter: CopywriterAgent,
        tracker: EmailTracker,
    ) -> None:
        self._session_factory = session_factory
        self._redis_url = redis_url
        self._email_sender = email_sender
        self._copywriter = copywriter
        self._tracker = tracker
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def run_tick(self) -> None:
        """Execute one tick of the sequence runner.

        Iterates over all active campaigns, determines which leads need
        their next message sent, and sends them.
        """
        logger.info("Sequence runner tick started")
        async with self._session_factory() as session:
            # Query all active campaigns with their sequences loaded
            stmt = (
                select(Campaign)
                .options(selectinload(Campaign.sequence))
                .where(Campaign.status == CampaignStatus.active)
            )
            result = await session.execute(stmt)
            campaigns = result.scalars().all()

            logger.info("Found %d active campaigns", len(campaigns))

            for campaign in campaigns:
                try:
                    await self._process_campaign(session, campaign)
                except Exception as exc:
                    logger.error(
                        "Error processing campaign %s: %s",
                        campaign.id,
                        exc,
                        exc_info=True,
                    )

        logger.info("Sequence runner tick completed")

    async def _process_campaign(
        self, session: AsyncSession, campaign: Campaign
    ) -> None:
        """Process a single campaign: check each lead and send if due."""
        sequence = campaign.sequence
        if sequence is None:
            logger.warning(
                "Campaign %s has no sequence assigned, skipping", campaign.id
            )
            return

        steps: list[dict[str, Any]] = sequence.steps or []
        if not steps:
            logger.warning(
                "Campaign %s sequence has no steps, skipping", campaign.id
            )
            return

        leads = await self._get_campaign_leads(session, campaign)
        logger.info(
            "Campaign %s: processing %d eligible leads",
            campaign.id,
            len(leads),
        )

        for lead in leads:
            try:
                await self._process_lead(session, campaign, lead, steps)
            except Exception as exc:
                logger.error(
                    "Error processing lead %s in campaign %s: %s",
                    lead.id,
                    campaign.id,
                    exc,
                    exc_info=True,
                )

    async def _process_lead(
        self,
        session: AsyncSession,
        campaign: Campaign,
        lead: Lead,
        steps: list[dict[str, Any]],
    ) -> None:
        """Process a single lead: determine step, check timing, send if ready."""
        # Count how many outbound messages have been sent for this lead+campaign
        sent_count = await self._count_sent_messages(session, campaign.id, lead.id)

        # If all steps are complete, skip
        if sent_count >= len(steps):
            return

        step_index = sent_count
        step_config = steps[step_index]
        delay_days = step_config.get("delay_days", 0)

        # For the first message, no delay check needed beyond delay_days=0
        if step_index > 0:
            # Get the last sent message to check delay
            last_msg = await self._get_last_sent_message(
                session, campaign.id, lead.id
            )
            if last_msg is None:
                return
            if last_msg.sent_at is None:
                return

            required_time = last_msg.sent_at + timedelta(days=delay_days)
            now = datetime.now(timezone.utc)
            if now < required_time:
                return  # Delay hasn't elapsed yet

        # Acquire distributed lock to prevent double-sending
        redis = await self._get_redis()
        lock_key = f"lock:send:{campaign.id}:{lead.id}"
        lock_acquired = await redis.set(lock_key, "1", nx=True, ex=300)
        if not lock_acquired:
            logger.debug(
                "Lock not acquired for campaign=%s lead=%s, skipping",
                campaign.id,
                lead.id,
            )
            return

        try:
            await self._send_step_message(
                session, campaign, lead, step_config
            )
        finally:
            # Release the lock after sending
            await redis.delete(lock_key)

    async def _send_step_message(
        self,
        session: AsyncSession,
        campaign: Campaign,
        lead: Lead,
        step_config: dict[str, Any],
    ) -> None:
        """Generate and send the message for a step, then record in DB."""
        step_type = step_config.get("step_type", "initial")

        # Build lead dict for copywriter
        lead_dict: dict[str, Any] = {
            "first_name": lead.first_name,
            "last_name": lead.last_name,
            "email": lead.email,
            "company": lead.company,
            "title": lead.title,
            "enrichment_data": lead.enrichment_data or {},
        }

        # Build campaign context from campaign settings
        campaign_settings = campaign.icp_filter or {}
        campaign_context: dict[str, Any] = {
            "sender_name": campaign_settings.get("sender_name", ""),
            "sender_title": campaign_settings.get("sender_title", ""),
            "company_name": campaign_settings.get("company_name", ""),
            "value_proposition": campaign_settings.get("value_proposition", ""),
            "tone_of_voice": campaign_settings.get("tone_of_voice", "professional"),
        }

        # Check for active A/B test and apply variant configuration
        ab_test_stmt = select(ABTest).where(
            ABTest.campaign_id == campaign.id,
            ABTest.status == ABTestStatus.running,
        )
        ab_test_result = await session.execute(ab_test_stmt)
        active_test = ab_test_result.scalars().first()

        variant_config: dict[str, Any] | None = None
        if active_test:
            # Use OptimizerAgent.assign_variant to get or create the assignment
            from agents.optimizer import OptimizerAgent
            from core.config import settings
            from core.llm import LLMClient

            # Instantiate a lightweight optimizer for variant assignment
            llm_client = LLMClient(provider="openai", api_key=settings.openai_api_key, model="gpt-4")
            optimizer = OptimizerAgent(
                llm_client=llm_client,
                session_factory=self._session_factory,
                redis_url=self._redis_url,
            )
            variant_key = await optimizer.assign_variant(active_test.id, lead.id, session)

            # Find the variant config matching the assigned key
            for v in (active_test.variants or []):
                if v.get("key") == variant_key:
                    variant_config = v
                    break

        # Apply variant overrides to campaign context if A/B test active
        if variant_config:
            if variant_config.get("subject"):
                campaign_context["subject_override"] = variant_config["subject"]
            if variant_config.get("body"):
                campaign_context["body_override"] = variant_config["body"]
            if variant_config.get("template_config"):
                campaign_context["template_config"] = variant_config["template_config"]

        # Generate message content via copywriter
        message_content = await self._copywriter.write_message(
            lead_dict, campaign_context, step_type
        )

        subject = message_content["subject"]
        body = message_content["body"]

        if not subject or not body:
            logger.warning(
                "Empty message generated for lead %s step %s, skipping",
                lead.id,
                step_type,
            )
            return

        # Create message record
        message_id = uuid.uuid4()
        message_id_str = str(message_id)

        # Generate tracking URLs
        tracking_pixel_url = self._tracker.generate_tracking_pixel_url(message_id_str)
        click_url = self._tracker.generate_click_url(message_id_str, body)

        # Send email
        send_result = await self._email_sender.send_email(
            to=lead.email,
            subject=subject,
            html_body=body,
            message_id=message_id_str,
            tracking_pixel_url=tracking_pixel_url,
            tracked_links=None,
        )

        if not send_result.get("success"):
            logger.warning(
                "Failed to send email to %s for campaign %s",
                lead.email,
                campaign.id,
            )
            return

        # Record message in database
        now = datetime.now(timezone.utc)
        msg_record = Message(
            id=message_id,
            lead_id=lead.id,
            campaign_id=campaign.id,
            channel=ChannelType.email,
            direction=MessageDirection.outbound,
            content=body,
            subject=subject,
            status=MessageStatus.sent,
            sent_at=now,
            meta={
                "step_type": step_type,
                "domain_used": send_result.get("domain_used"),
                "message_id_header": send_result.get("message_id_header"),
            },
        )
        session.add(msg_record)

        # Update lead status to contacted if still new
        if lead.status == LeadStatus.new:
            lead.status = LeadStatus.contacted

        await session.commit()
        logger.info(
            "Sent %s email to %s (lead=%s, campaign=%s)",
            step_type,
            lead.email,
            lead.id,
            campaign.id,
        )

    async def _get_campaign_leads(
        self, session: AsyncSession, campaign: Campaign
    ) -> list[Lead]:
        """Query leads assigned to this campaign that are eligible for messaging.

        A lead is considered assigned to this campaign if it has at least one
        Message record (any status/direction) for this campaign_id.
        """
        # Subquery: lead IDs that have at least one message in this campaign
        lead_ids_subq = (
            select(Message.lead_id)
            .where(Message.campaign_id == campaign.id)
            .distinct()
            .subquery()
        )
        stmt = (
            select(Lead)
            .where(Lead.id.in_(select(lead_ids_subq.c.lead_id)))
            .where(Lead.status.notin_([s.value for s in _SKIP_STATUSES]))
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _count_sent_messages(
        self,
        session: AsyncSession,
        campaign_id: uuid.UUID,
        lead_id: uuid.UUID,
    ) -> int:
        """Count outbound messages sent for a specific campaign+lead pair."""
        stmt = (
            select(func.count())
            .select_from(Message)
            .where(Message.campaign_id == campaign_id)
            .where(Message.lead_id == lead_id)
            .where(Message.direction == MessageDirection.outbound)
            .where(Message.status != MessageStatus.draft)
        )
        result = await session.execute(stmt)
        return result.scalar() or 0

    async def _get_last_sent_message(
        self,
        session: AsyncSession,
        campaign_id: uuid.UUID,
        lead_id: uuid.UUID,
    ) -> Message | None:
        """Get the most recently sent outbound message for a campaign+lead pair."""
        stmt = (
            select(Message)
            .where(Message.campaign_id == campaign_id)
            .where(Message.lead_id == lead_id)
            .where(Message.direction == MessageDirection.outbound)
            .where(Message.status != MessageStatus.draft)
            .order_by(Message.sent_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
