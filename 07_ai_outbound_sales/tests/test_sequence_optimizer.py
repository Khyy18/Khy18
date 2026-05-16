"""Tests for Smart Sequencing / Sequence Optimizer Agent."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from agents.sequence_optimizer import NextAction, SequenceOptimizerAgent
from core.models import (
    Call,
    CallOutcome,
    CallStatus,
    ChannelType,
    Event,
    EventType,
    Lead,
    LeadInteraction,
    Message,
    MessageDirection,
    MessageStatus,
)
from scheduler.channel_router import ChannelRouter
from tests.conftest import (
    make_call,
    make_campaign,
    make_event,
    make_lead,
    make_lead_interaction,
    make_message,
    make_tenant,
)


# ---------- NextAction Model Tests ----------


class TestNextAction:
    """Tests for the NextAction Pydantic model."""

    def test_create_next_action(self):
        """NextAction model can be created with all fields."""
        action = NextAction(
            channel="voice",
            delay_hours=2,
            reasoning="Email opened, time to call",
            confidence=0.8,
        )
        assert action.channel == "voice"
        assert action.delay_hours == 2
        assert action.reasoning == "Email opened, time to call"
        assert action.confidence == 0.8

    def test_next_action_serialization(self):
        """NextAction can be serialized to dict."""
        action = NextAction(
            channel="email",
            delay_hours=0,
            reasoning="Starting outreach",
            confidence=0.5,
        )
        d = action.model_dump()
        assert d["channel"] == "email"
        assert d["delay_hours"] == 0


# ---------- Rules Engine Tests ----------


class TestRulesEngine:
    """Tests for the sequence optimizer rules engine."""

    async def test_email_opened_no_reply_recommends_call(
        self, async_session, session_factory, mock_llm_client
    ):
        """Rule: Email opened but no reply after 24h -> recommend call in 2h."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        campaign = make_campaign(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        async_session.add(campaign)
        await async_session.commit()

        # Create an opened email from 25 hours ago
        msg = make_message(
            lead_id=lead.id,
            campaign_id=campaign.id,
            channel=ChannelType.email,
            direction=MessageDirection.outbound,
            status=MessageStatus.opened,
        )
        msg.sent_at = datetime.now(timezone.utc) - timedelta(hours=25)
        async_session.add(msg)
        await async_session.commit()

        optimizer = SequenceOptimizerAgent(
            llm_client=mock_llm_client,
            session_factory=session_factory,
            settings=MagicMock(),
        )

        result = await optimizer.get_next_action(lead.id)
        assert result.channel == "voice"
        assert result.delay_hours == 2
        assert result.confidence >= 0.7

    async def test_call_no_answer_recommends_linkedin(
        self, async_session, session_factory, mock_llm_client
    ):
        """Rule: Call no-answer -> recommend LinkedIn message next day."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        # Create a no-answer call
        call = make_call(
            tenant_id=tenant.id,
            lead_id=lead.id,
            status=CallStatus.no_answer,
        )
        call.outcome = CallOutcome.no_answer
        async_session.add(call)
        await async_session.commit()

        optimizer = SequenceOptimizerAgent(
            llm_client=mock_llm_client,
            session_factory=session_factory,
            settings=MagicMock(),
        )

        result = await optimizer.get_next_action(lead.id)
        assert result.channel == "linkedin"
        assert result.delay_hours == 24

    async def test_multiple_no_answers_different_time(
        self, async_session, session_factory, mock_llm_client
    ):
        """Rule: Multiple no-answers -> recommend different time of day."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        # Create multiple no-answer calls
        for _ in range(2):
            call = make_call(
                tenant_id=tenant.id,
                lead_id=lead.id,
                status=CallStatus.no_answer,
            )
            call.outcome = CallOutcome.no_answer
            async_session.add(call)
        await async_session.commit()

        optimizer = SequenceOptimizerAgent(
            llm_client=mock_llm_client,
            session_factory=session_factory,
            settings=MagicMock(),
        )

        result = await optimizer.get_next_action(lead.id)
        assert result.channel == "voice"
        assert result.delay_hours == 28  # next day, different time

    async def test_linkedin_viewed_no_response_recommends_email(
        self, async_session, session_factory, mock_llm_client
    ):
        """Rule: LinkedIn viewed but no response -> recommend email follow-up."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        campaign = make_campaign(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        async_session.add(campaign)
        await async_session.commit()

        # Create a LinkedIn message that was viewed
        msg = make_message(
            lead_id=lead.id,
            campaign_id=campaign.id,
            channel=ChannelType.linkedin,
            direction=MessageDirection.outbound,
            status=MessageStatus.sent,
        )
        msg.meta = {"viewed": True}
        async_session.add(msg)
        await async_session.commit()

        optimizer = SequenceOptimizerAgent(
            llm_client=mock_llm_client,
            session_factory=session_factory,
            settings=MagicMock(),
        )

        result = await optimizer.get_next_action(lead.id)
        assert result.channel == "email"
        assert result.delay_hours == 24

    async def test_no_engagement_defaults_to_email(
        self, async_session, session_factory, mock_llm_client
    ):
        """Default: No prior engagement signals -> start with email."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        optimizer = SequenceOptimizerAgent(
            llm_client=mock_llm_client,
            session_factory=session_factory,
            settings=MagicMock(),
        )

        result = await optimizer.get_next_action(lead.id)
        assert result.channel == "email"
        assert result.delay_hours == 0
        assert result.confidence == 0.5

    async def test_lead_not_found_defaults(self, session_factory, mock_llm_client):
        """Non-existent lead returns default email action."""
        optimizer = SequenceOptimizerAgent(
            llm_client=mock_llm_client,
            session_factory=session_factory,
            settings=MagicMock(),
        )

        result = await optimizer.get_next_action(uuid.uuid4())
        assert result.channel == "email"
        assert result.confidence == 0.3


# ---------- Engagement Score Tests ----------


class TestEngagementScore:
    """Tests for engagement score calculation."""

    async def test_engagement_score_no_interactions(
        self, async_session, session_factory, mock_llm_client
    ):
        """Score is 0.0 when no interactions exist."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        optimizer = SequenceOptimizerAgent(
            llm_client=mock_llm_client,
            session_factory=session_factory,
            settings=MagicMock(),
        )

        score = await optimizer.calculate_engagement_score(lead.id)
        assert score == 0.0

    async def test_engagement_score_with_interactions(
        self, async_session, session_factory, mock_llm_client
    ):
        """Score increases with interactions."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        # Add recent interactions
        for i in range(3):
            interaction = make_lead_interaction(
                lead_id=lead.id,
                tenant_id=tenant.id,
                interaction_type="email",
                channel="email",
                summary=f"Interaction {i}",
            )
            async_session.add(interaction)
        await async_session.commit()

        optimizer = SequenceOptimizerAgent(
            llm_client=mock_llm_client,
            session_factory=session_factory,
            settings=MagicMock(),
        )

        score = await optimizer.calculate_engagement_score(lead.id)
        assert score > 0.0
        assert score <= 1.0

    async def test_engagement_score_with_answered_call(
        self, async_session, session_factory, mock_llm_client
    ):
        """Score increases with answered calls."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        call = make_call(
            tenant_id=tenant.id,
            lead_id=lead.id,
            status=CallStatus.answered,
        )
        async_session.add(call)
        await async_session.commit()

        optimizer = SequenceOptimizerAgent(
            llm_client=mock_llm_client,
            session_factory=session_factory,
            settings=MagicMock(),
        )

        score = await optimizer.calculate_engagement_score(lead.id)
        assert score >= 0.2


# ---------- Channel Router Integration Tests ----------


class TestChannelRouterIntegration:
    """Tests for sequence optimizer integration with ChannelRouter."""

    async def test_get_optimized_next_action(
        self, async_session, session_factory, mock_llm_client
    ):
        """ChannelRouter.get_optimized_next_action returns optimizer result."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        router = ChannelRouter(session_factory=session_factory)
        result = await router.get_optimized_next_action(
            lead_id=lead.id,
            llm_client=mock_llm_client,
            settings=MagicMock(),
        )

        assert result is not None
        assert "channel" in result
        assert "delay_hours" in result
        assert "reasoning" in result
        assert "confidence" in result

    async def test_get_optimized_next_action_no_client(self, session_factory):
        """get_optimized_next_action returns None when no LLM client provided."""
        router = ChannelRouter(session_factory=session_factory)
        result = await router.get_optimized_next_action(
            lead_id=uuid.uuid4(),
            llm_client=None,
            settings=None,
        )
        assert result is None
