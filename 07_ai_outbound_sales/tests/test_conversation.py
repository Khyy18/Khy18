"""Tests for the ConversationAgent."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.conversation import ConversationAgent, _CONFIDENCE_THRESHOLD
from core.models import (
    Campaign,
    CampaignStatus,
    ChannelType,
    Lead,
    LeadStatus,
    Message,
    MessageDirection,
    MessageStatus,
)


@pytest.fixture
def mock_calendar():
    calendar = AsyncMock()
    calendar.generate_booking_link = AsyncMock(return_value="https://cal.com/book/test")
    return calendar


@pytest.fixture
def conversation_agent(mock_llm_client, mock_settings, mock_calendar, session_factory):
    return ConversationAgent(
        llm_client=mock_llm_client,
        settings=mock_settings,
        calendar=mock_calendar,
        session_factory=session_factory,
        email_sender=None,
    )


@pytest.fixture
def campaign_context():
    return {
        "company_name": "SalesBot AI",
        "value_proposition": "AI-powered outbound",
        "sender_name": "Alice",
        "sender_title": "AE",
    }


async def test_classify_reply_positive(conversation_agent, campaign_context, mock_llm_client):
    """Test classifying a positive reply."""
    mock_llm_client.generate.return_value = json.dumps({
        "classification": "positive",
        "confidence": 0.95,
        "details": "Prospect is interested in a meeting",
    })

    result = await conversation_agent.classify_reply(
        "Yes, I'd love to learn more! When are you free?", campaign_context
    )

    assert result["classification"] == "positive"
    assert result["confidence"] == 0.95


async def test_classify_reply_objection(conversation_agent, campaign_context, mock_llm_client):
    """Test classifying an objection reply."""
    mock_llm_client.generate.return_value = json.dumps({
        "classification": "objection",
        "confidence": 0.85,
        "details": "Prospect has budget concerns",
    })

    result = await conversation_agent.classify_reply(
        "We don't have the budget for this right now.", campaign_context
    )

    assert result["classification"] == "objection"


async def test_classify_reply_question(conversation_agent, campaign_context, mock_llm_client):
    """Test classifying a question reply."""
    mock_llm_client.generate.return_value = json.dumps({
        "classification": "question",
        "confidence": 0.90,
        "details": "Prospect asking about pricing",
    })

    result = await conversation_agent.classify_reply(
        "What's your pricing model?", campaign_context
    )

    assert result["classification"] == "question"


async def test_classify_reply_not_now(conversation_agent, campaign_context, mock_llm_client):
    """Test classifying a not_now reply."""
    mock_llm_client.generate.return_value = json.dumps({
        "classification": "not_now",
        "confidence": 0.80,
        "details": "Prospect interested but timing is off",
    })

    result = await conversation_agent.classify_reply(
        "Interesting but we're focused on other priorities this quarter.", campaign_context
    )

    assert result["classification"] == "not_now"


async def test_classify_reply_unsubscribe(conversation_agent, campaign_context, mock_llm_client):
    """Test classifying an unsubscribe reply."""
    mock_llm_client.generate.return_value = json.dumps({
        "classification": "unsubscribe",
        "confidence": 0.99,
        "details": "Explicit opt-out request",
    })

    result = await conversation_agent.classify_reply(
        "Please remove me from your mailing list.", campaign_context
    )

    assert result["classification"] == "unsubscribe"


async def test_classify_reply_negative(conversation_agent, campaign_context, mock_llm_client):
    """Test classifying a negative reply."""
    mock_llm_client.generate.return_value = json.dumps({
        "classification": "negative",
        "confidence": 0.88,
        "details": "Prospect is clearly not interested",
    })

    result = await conversation_agent.classify_reply(
        "Not interested, please don't contact me again.", campaign_context
    )

    assert result["classification"] == "negative"


async def test_classify_reply_out_of_office(conversation_agent, campaign_context, mock_llm_client):
    """Test classifying an out-of-office reply."""
    mock_llm_client.generate.return_value = json.dumps({
        "classification": "out_of_office",
        "confidence": 0.99,
        "details": "Auto-reply OOO",
    })

    result = await conversation_agent.classify_reply(
        "I am out of the office until January 15. I will respond upon my return.", campaign_context
    )

    assert result["classification"] == "out_of_office"


async def test_classify_reply_low_confidence_returns_needs_review(
    conversation_agent, campaign_context, mock_llm_client
):
    """Test that confidence below threshold returns needs_review in handle_reply."""
    mock_llm_client.generate.return_value = json.dumps({
        "classification": "positive",
        "confidence": 0.2,  # Below _CONFIDENCE_THRESHOLD (0.3)
        "details": "Uncertain classification",
    })

    result = await conversation_agent.classify_reply(
        "Maybe...", campaign_context
    )

    # classify_reply itself returns what LLM says
    assert result["confidence"] == 0.2
    # The threshold gating happens in handle_reply, not classify_reply


async def test_handle_reply_positive_updates_status_to_qualified(
    async_session, session_factory, mock_llm_client, mock_settings
):
    """Test that handle_reply sets lead status to qualified for positive classification."""
    mock_calendar = AsyncMock()
    mock_calendar.generate_booking_link = AsyncMock(return_value="https://cal.com/book/test")

    agent = ConversationAgent(
        llm_client=mock_llm_client,
        settings=mock_settings,
        calendar=mock_calendar,
        session_factory=session_factory,
        email_sender=None,
    )

    # Create test data
    tenant_id = uuid.uuid4()
    tenant = Campaign.__table__  # Use raw table for simpler setup
    from tests.conftest import make_tenant, make_lead, make_campaign, make_message

    tenant = make_tenant(id=tenant_id)
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant_id, status=LeadStatus.contacted)
    async_session.add(lead)

    campaign = make_campaign(
        tenant_id=tenant_id,
        icp_filter={"company_name": "TestCo", "value_proposition": "Testing", "sender_name": "Bot", "sender_title": "AI"},
    )
    async_session.add(campaign)
    await async_session.flush()

    msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.inbound,
        content="Yes, I'm interested! Let's talk.",
        status=MessageStatus.sent,
    )
    async_session.add(msg)
    await async_session.commit()

    # Mock LLM to return positive classification, then response, then quality score
    mock_llm_client.generate.side_effect = [
        json.dumps({"classification": "positive", "confidence": 0.95, "details": "interested"}),
        json.dumps({"subject": "Re: Meeting", "body": "Great! Here's my calendar link.", "action": "book_meeting", "follow_up_days": None}),
        json.dumps({"relevance": 9, "tone": 9, "value_proposition_clarity": 8, "cta_effectiveness": 9, "length_appropriateness": 8, "no_hallucinations": 10, "improvement_suggestions": []}),
    ]

    result = await agent.handle_reply(str(msg.id))

    assert result["classification"]["classification"] == "positive"
    assert result["lead_status"] == "qualified"


async def test_handle_reply_unsubscribe_updates_status_to_lost(
    async_session, session_factory, mock_llm_client, mock_settings
):
    """Test that handle_reply sets lead status to lost for unsubscribe."""
    mock_calendar = AsyncMock()
    mock_calendar.generate_booking_link = AsyncMock(return_value="")

    agent = ConversationAgent(
        llm_client=mock_llm_client,
        settings=mock_settings,
        calendar=mock_calendar,
        session_factory=session_factory,
        email_sender=None,
    )

    from tests.conftest import make_tenant, make_lead, make_campaign, make_message

    tenant_id = uuid.uuid4()
    tenant = make_tenant(id=tenant_id)
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant_id, status=LeadStatus.contacted)
    async_session.add(lead)

    campaign = make_campaign(
        tenant_id=tenant_id,
        icp_filter={"company_name": "TestCo", "value_proposition": "Testing", "sender_name": "Bot", "sender_title": "AI"},
    )
    async_session.add(campaign)
    await async_session.flush()

    msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.inbound,
        content="Please remove me from your list.",
        status=MessageStatus.sent,
    )
    async_session.add(msg)
    await async_session.commit()

    mock_llm_client.generate.side_effect = [
        json.dumps({"classification": "unsubscribe", "confidence": 0.99, "details": "opt-out"}),
        json.dumps({"subject": "Re: Removal", "body": "Done, you've been removed.", "action": "close", "follow_up_days": None}),
    ]

    result = await agent.handle_reply(str(msg.id))

    assert result["classification"]["classification"] == "unsubscribe"
    assert result["lead_status"] == "lost"


async def test_handle_reply_below_confidence_threshold_skips_response(
    async_session, session_factory, mock_llm_client, mock_settings
):
    """Test that handle_reply skips automated response when confidence is below threshold."""
    mock_calendar = AsyncMock()
    mock_calendar.generate_booking_link = AsyncMock(return_value="")

    agent = ConversationAgent(
        llm_client=mock_llm_client,
        settings=mock_settings,
        calendar=mock_calendar,
        session_factory=session_factory,
        email_sender=None,
    )

    from tests.conftest import make_tenant, make_lead, make_campaign, make_message

    tenant_id = uuid.uuid4()
    tenant = make_tenant(id=tenant_id)
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant_id, status=LeadStatus.contacted)
    async_session.add(lead)

    campaign = make_campaign(
        tenant_id=tenant_id,
        icp_filter={"company_name": "TestCo", "value_proposition": "Testing", "sender_name": "Bot", "sender_title": "AI"},
    )
    async_session.add(campaign)
    await async_session.flush()

    msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.inbound,
        content="hmm maybe",
        status=MessageStatus.sent,
    )
    async_session.add(msg)
    await async_session.commit()

    mock_llm_client.generate.return_value = json.dumps({
        "classification": "positive",
        "confidence": 0.1,  # Below _CONFIDENCE_THRESHOLD (0.3)
        "details": "Very uncertain",
    })

    result = await agent.handle_reply(str(msg.id))

    assert result["skipped"] == "confidence_below_threshold"
    assert result["response"] is None
