"""Channel Router - determines channel routing, prerequisites, and cross-channel coordination."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import (
    ChannelType,
    Event,
    EventType,
    Lead,
    LeadStatus,
    Message,
    MessageDirection,
    MessageStatus,
)

logger = logging.getLogger(__name__)

# Valid channel types for sequence steps
VALID_CHANNELS = {"email", "linkedin_view", "linkedin_connect", "linkedin_message"}


class ChannelRouter:
    """Routes sequence steps to the appropriate channel and handles cross-channel coordination."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the ChannelRouter.

        Args:
            session_factory: Async session factory for database access.
        """
        self._session_factory = session_factory

    def determine_channel(self, step_config: dict[str, Any]) -> str:
        """Determine the channel type from a step configuration.

        For backward compatibility, if step has "step_type" but no "channel" field,
        defaults to "email".

        Args:
            step_config: The step configuration dictionary.

        Returns:
            The channel type string (email/linkedin_view/linkedin_connect/linkedin_message).
        """
        if "channel" in step_config:
            return step_config["channel"]
        # Legacy step_type without channel field defaults to email
        return "email"

    async def should_skip_lead(
        self,
        lead_id: uuid.UUID,
        campaign_id: uuid.UUID,
        session: AsyncSession,
    ) -> bool:
        """Check if lead should be skipped because they already replied on ANY channel.

        Returns True if lead already replied on any channel (check Messages table for
        inbound messages with status replied, or Lead.status == replied/booked).

        Args:
            lead_id: The lead's UUID.
            campaign_id: The campaign's UUID.
            session: The async database session.

        Returns:
            True if the lead should be skipped, False otherwise.
        """
        # Check lead status
        lead_result = await session.execute(
            select(Lead).where(Lead.id == lead_id)
        )
        lead = lead_result.scalar_one_or_none()
        if lead is None:
            return True

        if lead.status in (LeadStatus.replied, LeadStatus.booked):
            return True

        # Check for inbound messages with replied status for this campaign
        replied_msg_stmt = (
            select(Message)
            .where(Message.lead_id == lead_id)
            .where(Message.campaign_id == campaign_id)
            .where(Message.direction == MessageDirection.inbound)
            .where(Message.status == MessageStatus.replied)
            .limit(1)
        )
        result = await session.execute(replied_msg_stmt)
        if result.scalar_one_or_none() is not None:
            return True

        return False

    async def calculate_delay(
        self,
        step_config: dict[str, Any],
        lead_id: uuid.UUID,
        campaign_id: uuid.UUID,
        session: AsyncSession,
    ) -> timedelta:
        """Calculate the delay for a step, considering cross-channel signals.

        Base delay comes from step_config["delay_days"]. If the channel is
        linkedin_connect and the lead has email open events, add 2 extra days.

        Args:
            step_config: The step configuration dictionary.
            lead_id: The lead's UUID.
            campaign_id: The campaign's UUID.
            session: The async database session.

        Returns:
            A timedelta representing the calculated delay.
        """
        delay_days = step_config.get("delay_days", 0)
        channel = self.determine_channel(step_config)

        if channel == "linkedin_connect":
            # Check if the lead has email open events for this campaign
            open_event_stmt = (
                select(Event)
                .join(Message, Event.message_id == Message.id)
                .where(Message.lead_id == lead_id)
                .where(Message.campaign_id == campaign_id)
                .where(Message.channel == ChannelType.email)
                .where(Event.event_type == EventType.open)
                .limit(1)
            )
            result = await session.execute(open_event_stmt)
            if result.scalar_one_or_none() is not None:
                delay_days += 2

        return timedelta(days=delay_days)

    async def check_prerequisites(
        self,
        step_config: dict[str, Any],
        lead_id: uuid.UUID,
        session: AsyncSession,
    ) -> bool:
        """Check whether prerequisites are met for a step.

        For linkedin_message, check that a linkedin_connect message was previously
        sent and marked as sent for this lead.

        Args:
            step_config: The step configuration dictionary.
            lead_id: The lead's UUID.
            session: The async database session.

        Returns:
            True if prerequisites are met, False otherwise.
        """
        channel = self.determine_channel(step_config)

        if channel == "linkedin_message":
            # Check for a prior linkedin_connect message that was sent
            connect_msg_stmt = (
                select(Message)
                .where(Message.lead_id == lead_id)
                .where(Message.channel == ChannelType.linkedin)
                .where(Message.direction == MessageDirection.outbound)
                .where(Message.status.in_([MessageStatus.sent, MessageStatus.draft]))
                .where(Message.meta["linkedin_task"].as_string() == "linkedin_connect_task")
                .limit(1)
            )
            result = await session.execute(connect_msg_stmt)
            if result.scalar_one_or_none() is None:
                return False

        return True

    async def check_deduplication(
        self,
        lead_id: uuid.UUID,
        campaign_id: uuid.UUID,
        session: AsyncSession,
    ) -> bool:
        """Check for cross-channel deduplication.

        Returns True (skip) if lead already replied via email and we are about to
        send LinkedIn, or vice versa.

        Args:
            lead_id: The lead's UUID.
            campaign_id: The campaign's UUID.
            session: The async database session.

        Returns:
            True if the step should be skipped (duplicate), False otherwise.
        """
        # Check if lead replied via any channel for this campaign
        replied_stmt = (
            select(Message)
            .where(Message.lead_id == lead_id)
            .where(Message.campaign_id == campaign_id)
            .where(Message.direction == MessageDirection.inbound)
            .where(Message.status == MessageStatus.replied)
            .limit(1)
        )
        result = await session.execute(replied_stmt)
        if result.scalar_one_or_none() is not None:
            return True

        return False
