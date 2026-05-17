"""Tests for the AutoApproveEngine."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.auto_approve import AutoApproveEngine, AutoApproveResult
from agents.conversation import ConversationAgent
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
def auto_approve_settings():
    """Settings fixture with auto_approve explicitly enabled (boolean True)."""
    s = MagicMock()
    s.auto_approve_enabled = True
    s.auto_approve_quality_threshold = 75
    s.protected_companies_list = '["Google", "Apple"]'
    s.auto_approve_max_retries = 3
    s.approval_required_company_size = 500
    return s


@pytest.fixture
def auto_approve_engine(mock_llm_client, auto_approve_settings):
    """Create an AutoApproveEngine instance with test fixtures."""
    return AutoApproveEngine(
        llm_client=mock_llm_client,
        settings=auto_approve_settings,
    )


# --- Safety Check: No Pricing Promises ---

async def test_check_no_pricing_promises_detects_dollar_sign(auto_approve_engine):
    """Text with $ amounts should fail pricing check."""
    assert auto_approve_engine._check_no_pricing_promises("Our plan is $99/month") is False


async def test_check_no_pricing_promises_detects_keywords(auto_approve_engine):
    """Text with pricing keywords should fail."""
    assert auto_approve_engine._check_no_pricing_promises("We can offer a discount") is False
    assert auto_approve_engine._check_no_pricing_promises("Check our pricing page") is False
    assert auto_approve_engine._check_no_pricing_promises("The cost is very reasonable") is False


async def test_check_no_pricing_promises_passes_clean_text(auto_approve_engine):
    """Clean text without pricing references should pass."""
    assert auto_approve_engine._check_no_pricing_promises(
        "I would love to schedule a meeting to discuss how we can help your team."
    ) is True


# --- Safety Check: No Timeline Commitments ---

async def test_check_no_timeline_commitments_detects_deadline(auto_approve_engine):
    """Text with timeline commitments should fail."""
    assert auto_approve_engine._check_no_timeline_commitments("We can deliver by Monday") is False
    assert auto_approve_engine._check_no_timeline_commitments("within 3 days") is False
    assert auto_approve_engine._check_no_timeline_commitments("by end of the week") is False


async def test_check_no_timeline_commitments_passes_clean_text(auto_approve_engine):
    """Clean text without timeline commitments should pass."""
    assert auto_approve_engine._check_no_timeline_commitments(
        "Let me know when you are available to connect."
    ) is True


# --- Safety Check: Word Limit ---

async def test_check_word_limit_fails_over_300(auto_approve_engine):
    """Text over 300 words should fail word limit check."""
    long_text = " ".join(["word"] * 301)
    assert auto_approve_engine._check_word_limit(long_text) is False


async def test_check_word_limit_passes_under_300(auto_approve_engine):
    """Text under 300 words should pass word limit check."""
    short_text = " ".join(["word"] * 100)
    assert auto_approve_engine._check_word_limit(short_text) is True


# --- Safety Check: No Profanity ---

async def test_check_no_profanity_detects_bad_words(auto_approve_engine):
    """Text with profanity should fail."""
    assert auto_approve_engine._check_no_profanity("This is a damn good offer") is False
    assert auto_approve_engine._check_no_profanity("What the hell are you waiting for") is False


async def test_check_no_profanity_passes_clean_text(auto_approve_engine):
    """Clean professional text should pass profanity check."""
    assert auto_approve_engine._check_no_profanity(
        "I would be happy to arrange a brief call at your convenience."
    ) is True


# --- Safety Check: Protected Company ---

async def test_check_protected_company_blocks_fortune500(auto_approve_engine):
    """Protected companies (like Google, Apple) should be blocked."""
    assert auto_approve_engine._check_protected_company("Google") is False
    assert auto_approve_engine._check_protected_company("Apple") is False
    assert auto_approve_engine._check_protected_company("google") is False


async def test_check_protected_company_passes_regular(auto_approve_engine):
    """Non-protected companies should pass."""
    assert auto_approve_engine._check_protected_company("Acme Inc") is True
    assert auto_approve_engine._check_protected_company("StartupCo") is True


# --- Safety Check: No Competitor Mentions ---

async def test_check_no_competitor_mentions_detects(auto_approve_engine):
    """Text mentioning competitors should fail."""
    assert auto_approve_engine._check_no_competitor_mentions(
        "Unlike Salesforce, we offer better service", ["Salesforce", "HubSpot"]
    ) is False


async def test_check_no_competitor_mentions_passes(auto_approve_engine):
    """Text without competitor mentions should pass."""
    assert auto_approve_engine._check_no_competitor_mentions(
        "Our platform helps teams grow", ["Salesforce", "HubSpot"]
    ) is True


# --- Evaluate: All Pass Approves ---

async def test_evaluate_all_pass_approves(auto_approve_engine, mock_llm_client):
    """When all safety checks pass and quality >= threshold, should approve."""
    # Mock quality scorer to return high score (80/100)
    mock_llm_client.generate.return_value = json.dumps({
        "relevance": 9,
        "tone": 8,
        "value_proposition_clarity": 8,
        "cta_effectiveness": 8,
        "length_appropriateness": 8,
        "no_hallucinations": 9,
        "improvement_suggestions": [],
    })

    result = await auto_approve_engine.evaluate(
        proposed_response={"body": "Let us schedule a call to discuss how we can help your team.", "subject": "Re: Follow up", "action": "send_reply"},
        lead_data={"first_name": "John", "last_name": "Doe", "company": "Acme Inc", "original_message": "Tell me more"},
        campaign_context={"company_name": "TestCo", "value_proposition": "AI sales"},
    )

    assert result.approved is True
    assert result.quality_score >= 75
    assert all(result.safety_checks.values())


# --- Evaluate: Low Quality Regenerates ---

async def test_evaluate_low_quality_regenerates(auto_approve_engine, mock_llm_client):
    """When quality is 60-75, should recommend regeneration."""
    # Mock quality scorer to return score of ~68 (between 60 and 75)
    mock_llm_client.generate.return_value = json.dumps({
        "relevance": 7,
        "tone": 7,
        "value_proposition_clarity": 7,
        "cta_effectiveness": 6,
        "length_appropriateness": 7,
        "no_hallucinations": 7,
        "improvement_suggestions": ["Could be more specific"],
    })

    result = await auto_approve_engine.evaluate(
        proposed_response={"body": "Let me know if you want to chat.", "subject": "Re: Info", "action": "send_reply"},
        lead_data={"first_name": "Jane", "last_name": "Smith", "company": "Acme Inc", "original_message": "Maybe"},
        campaign_context={"company_name": "TestCo", "value_proposition": "AI sales"},
    )

    assert result.approved is False
    assert result.should_regenerate is True
    assert 60 <= result.quality_score < 75


# --- Evaluate: Very Low Quality Rejects ---

async def test_evaluate_very_low_quality_rejects(auto_approve_engine, mock_llm_client):
    """When quality < 60, should reject without regeneration."""
    # Mock quality scorer to return low score (~48)
    mock_llm_client.generate.return_value = json.dumps({
        "relevance": 5,
        "tone": 5,
        "value_proposition_clarity": 4,
        "cta_effectiveness": 5,
        "length_appropriateness": 5,
        "no_hallucinations": 5,
        "improvement_suggestions": ["Needs major rewrite"],
    })

    result = await auto_approve_engine.evaluate(
        proposed_response={"body": "Ok.", "subject": "Re: Stuff", "action": "send_reply"},
        lead_data={"first_name": "Bob", "last_name": "Jones", "company": "Acme Inc", "original_message": "Hello"},
        campaign_context={"company_name": "TestCo", "value_proposition": "AI sales"},
    )

    assert result.approved is False
    assert result.should_regenerate is False
    assert result.quality_score < 60


# --- Evaluate: Safety Failure Rejects ---

async def test_evaluate_safety_failure_rejects(auto_approve_engine, mock_llm_client):
    """When quality is high but a safety check fails, should reject."""
    # Mock quality scorer to return high score (83)
    mock_llm_client.generate.return_value = json.dumps({
        "relevance": 9,
        "tone": 8,
        "value_proposition_clarity": 8,
        "cta_effectiveness": 8,
        "length_appropriateness": 9,
        "no_hallucinations": 8,
        "improvement_suggestions": [],
    })

    # Body contains pricing promise - should fail safety check
    result = await auto_approve_engine.evaluate(
        proposed_response={"body": "We can offer you a special discount of $50 off.", "subject": "Re: Offer", "action": "send_reply"},
        lead_data={"first_name": "Alice", "last_name": "Brown", "company": "Acme Inc", "original_message": "Interested"},
        campaign_context={"company_name": "TestCo", "value_proposition": "AI sales"},
    )

    assert result.approved is False
    assert result.should_regenerate is False
    assert result.safety_checks["no_pricing_promises"] is False


# --- Conversation Agent Integration Tests ---

async def test_conversation_routes_through_auto_approve_when_enabled(
    async_session, session_factory, mock_llm_client
):
    """Test that conversation agent uses auto-approve when enabled."""
    from tests.conftest import make_tenant, make_lead, make_campaign, make_message

    # Create settings with auto_approve_enabled = True (literal boolean)
    settings = MagicMock()
    settings.auto_approve_enabled = True
    settings.auto_approve_quality_threshold = 75
    settings.protected_companies_list = "[]"
    settings.auto_approve_max_retries = 3
    settings.approval_required_company_size = 500

    mock_calendar = AsyncMock()
    mock_calendar.generate_booking_link = AsyncMock(return_value="https://cal.com/book/test")

    mock_sender = AsyncMock()
    mock_sender.send_email = AsyncMock(return_value={"success": True})

    agent = ConversationAgent(
        llm_client=mock_llm_client,
        settings=settings,
        calendar=mock_calendar,
        session_factory=session_factory,
        email_sender=mock_sender,
    )

    tenant_id = uuid.uuid4()
    tenant = make_tenant(id=tenant_id)
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant_id, status=LeadStatus.contacted)
    async_session.add(lead)

    campaign = make_campaign(
        tenant_id=tenant_id,
        icp_filter={
            "company_name": "TestCo",
            "value_proposition": "Testing",
            "sender_name": "Bot",
            "sender_title": "AI",
        },
    )
    async_session.add(campaign)
    await async_session.flush()

    msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.inbound,
        content="Tell me more about your product.",
        status=MessageStatus.sent,
    )
    async_session.add(msg)
    await async_session.commit()

    # Mock LLM responses: classification, response generation, quality scoring for auto-approve
    mock_llm_client.generate.side_effect = [
        # Classification
        json.dumps({"classification": "question", "confidence": 0.9, "details": "asking about product"}),
        # Response generation
        json.dumps({"subject": "Re: Your question", "body": "Happy to share more details about our platform.", "action": "send_reply", "follow_up_days": None}),
        # Quality scoring in auto-approve (high score to pass)
        json.dumps({"relevance": 9, "tone": 9, "value_proposition_clarity": 8, "cta_effectiveness": 8, "length_appropriateness": 9, "no_hallucinations": 9, "improvement_suggestions": []}),
    ]

    result = await agent.handle_reply(str(msg.id))

    assert result.get("auto_approved") is True
    assert result["response_sent"] is True


async def test_conversation_skips_auto_approve_when_disabled(
    async_session, session_factory, mock_llm_client, mock_settings
):
    """Test that conversation agent skips auto-approve when disabled (MagicMock settings)."""
    from tests.conftest import make_tenant, make_lead, make_campaign, make_message

    # mock_settings from conftest uses MagicMock, so auto_approve_enabled is a Mock (not True)
    # This should cause the auto-approve block to be skipped
    mock_calendar = AsyncMock()
    mock_calendar.generate_booking_link = AsyncMock(return_value="https://cal.com/book/test")

    agent = ConversationAgent(
        llm_client=mock_llm_client,
        settings=mock_settings,
        calendar=mock_calendar,
        session_factory=session_factory,
        email_sender=None,
    )

    tenant_id = uuid.uuid4()
    tenant = make_tenant(id=tenant_id)
    async_session.add(tenant)

    lead = make_lead(tenant_id=tenant_id, status=LeadStatus.contacted)
    async_session.add(lead)

    campaign = make_campaign(
        tenant_id=tenant_id,
        icp_filter={
            "company_name": "TestCo",
            "value_proposition": "Testing",
            "sender_name": "Bot",
            "sender_title": "AI",
        },
    )
    async_session.add(campaign)
    await async_session.flush()

    msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.inbound,
        content="Sure, let us connect.",
        status=MessageStatus.sent,
    )
    async_session.add(msg)
    await async_session.commit()

    # Mock LLM responses: classification, response, quality scoring (existing flow)
    mock_llm_client.generate.side_effect = [
        json.dumps({"classification": "question", "confidence": 0.85, "details": "open to chat"}),
        json.dumps({"subject": "Re: Connect", "body": "Great, when works for you?", "action": "send_reply", "follow_up_days": None}),
        json.dumps({"relevance": 9, "tone": 9, "value_proposition_clarity": 8, "cta_effectiveness": 8, "length_appropriateness": 9, "no_hallucinations": 9, "improvement_suggestions": []}),
    ]

    result = await agent.handle_reply(str(msg.id))

    # Should NOT have auto_approved key since auto-approve was skipped
    assert result.get("auto_approved") is None
    # The existing flow should have processed it normally
    assert "classification" in result
