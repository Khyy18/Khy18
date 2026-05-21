"""Tests for reply quality scoring and integration with conversation/copywriter agents."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.reply_quality import (
    QUALITY_THRESHOLD,
    QualityScore,
    ReplyQualityScorer,
)


@pytest.fixture
def quality_scorer(mock_llm_client):
    """Create ReplyQualityScorer with mocked LLM client."""
    return ReplyQualityScorer(mock_llm_client)


@pytest.fixture
def high_quality_response():
    """LLM response for a high quality score."""
    return json.dumps({
        "relevance": 9,
        "tone": 8,
        "value_proposition_clarity": 9,
        "cta_effectiveness": 8,
        "length_appropriateness": 9,
        "no_hallucinations": 10,
        "improvement_suggestions": ["Consider adding a case study reference"],
    })


@pytest.fixture
def low_quality_response():
    """LLM response for a low quality score."""
    return json.dumps({
        "relevance": 4,
        "tone": 5,
        "value_proposition_clarity": 3,
        "cta_effectiveness": 4,
        "length_appropriateness": 5,
        "no_hallucinations": 6,
        "improvement_suggestions": [
            "Response lacks relevance to prospect's message",
            "Value proposition is unclear",
            "CTA is weak",
        ],
    })


@pytest.mark.asyncio
async def test_score_response_returns_quality_score(quality_scorer, mock_llm_client, high_quality_response):
    """Test ReplyQualityScorer.score_response returns QualityScore with all fields."""
    mock_llm_client.generate = AsyncMock(return_value=high_quality_response)

    result = await quality_scorer.score_response(
        response_text="Thanks for your interest! Let me tell you more about how we can help.",
        prospect_message="I'd like to learn more about your product.",
        campaign_context={"company_name": "TestCo", "value_proposition": "Save time with AI"},
    )

    assert isinstance(result, QualityScore)
    assert result.relevance == 9
    assert result.tone == 8
    assert result.value_proposition_clarity == 9
    assert result.cta_effectiveness == 8
    assert result.length_appropriateness == 9
    assert result.no_hallucinations == 10
    assert result.overall_score > 0
    assert result.overall_score <= 100
    assert isinstance(result.improvement_suggestions, list)
    assert result.passed is True


@pytest.mark.asyncio
async def test_score_below_threshold_sets_passed_false(quality_scorer, mock_llm_client, low_quality_response):
    """Test score below threshold sets passed=False."""
    mock_llm_client.generate = AsyncMock(return_value=low_quality_response)

    result = await quality_scorer.score_response(
        response_text="Here is some generic response.",
        prospect_message="What exactly does your product do?",
        campaign_context={"company_name": "TestCo", "value_proposition": "AI automation"},
    )

    assert result.passed is False
    assert result.overall_score < QUALITY_THRESHOLD
    assert len(result.improvement_suggestions) > 0


@pytest.mark.asyncio
async def test_quality_score_calculation():
    """Test overall_score calculation from individual criteria."""
    score = QualityScore(
        relevance=7,
        tone=7,
        value_proposition_clarity=7,
        cta_effectiveness=7,
        length_appropriateness=7,
        no_hallucinations=7,
        overall_score=0,
    )
    # (7+7+7+7+7+7) / 6 * 10 = 70
    assert score.overall_score == 70
    assert score.passed is True

    low_score = QualityScore(
        relevance=6,
        tone=6,
        value_proposition_clarity=6,
        cta_effectiveness=6,
        length_appropriateness=6,
        no_hallucinations=6,
        overall_score=0,
    )
    # (6*6) / 6 * 10 = 60
    assert low_score.overall_score == 60
    assert low_score.passed is False


@pytest.mark.asyncio
async def test_conversation_agent_routes_low_quality_to_approval(
    mock_llm_client, mock_settings, session_factory, async_session
):
    """Test conversation agent routes low quality responses to approval queue."""
    from tests.conftest import make_campaign, make_lead, make_message, make_tenant
    from core.models import MessageDirection, MessageStatus

    # Create test data with proper FK relationships
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    lead = make_lead(tenant_id=tenant.id)
    campaign = make_campaign(
        tenant_id=tenant.id,
        icp_filter={
            "company_name": "TestCo",
            "value_proposition": "AI sales",
            "sender_name": "John",
            "sender_title": "VP Sales",
        },
    )

    async_session.add_all([lead, campaign])
    await async_session.flush()

    msg = make_message(
        lead_id=lead.id,
        campaign_id=campaign.id,
        direction=MessageDirection.inbound,
        status=MessageStatus.sent,
        content="What does your product do?",
    )

    async_session.add(msg)
    await async_session.commit()

    # Mock LLM responses:
    # 1st call = classification (high confidence, question type)
    # 2nd call = response generation
    # 3rd call = quality scoring (low score)
    classification_response = json.dumps({
        "classification": "question",
        "confidence": 0.9,
        "details": "Prospect asking about product",
    })
    generated_response = json.dumps({
        "subject": "Re: Your question",
        "body": "Here is some info about our product.",
        "action": "send_reply",
        "follow_up_days": None,
    })
    low_quality_score = json.dumps({
        "relevance": 4,
        "tone": 5,
        "value_proposition_clarity": 3,
        "cta_effectiveness": 4,
        "length_appropriateness": 5,
        "no_hallucinations": 5,
        "improvement_suggestions": ["Needs more specific details"],
    })

    mock_llm_client.generate = AsyncMock(
        side_effect=[classification_response, generated_response, low_quality_score]
    )

    mock_calendar = AsyncMock()
    mock_calendar.generate_booking_link = AsyncMock(return_value="https://cal.com/test")

    from agents.conversation import ConversationAgent

    agent = ConversationAgent(
        llm_client=mock_llm_client,
        settings=mock_settings,
        calendar=mock_calendar,
        session_factory=session_factory,
        email_sender=None,
    )

    with patch("agents.conversation.notify_human", new_callable=AsyncMock) as mock_notify:
        result = await agent.handle_reply(str(msg.id))

    assert result.get("routed_to_approval") is True
    assert result.get("response_sent") is False
    assert result.get("quality_score") is not None
    assert result["quality_score"] < QUALITY_THRESHOLD


@pytest.mark.asyncio
async def test_copywriter_regeneration_on_low_quality(mock_llm_client, mock_settings):
    """Test copywriter regenerates messages up to 3 times if quality < 70."""
    from agents.copywriter import CopywriterAgent
    from agents.reply_quality import ReplyQualityScorer

    quality_scorer = ReplyQualityScorer(mock_llm_client)

    # Mock LLM responses for write_message and quality scoring
    # First generate: low quality response
    # Second generate (quality score for first): low score
    # Third generate (regeneration 1): better response
    # Fourth generate (quality score for regen 1): high score
    call_count = [0]

    async def mock_generate(messages, temperature=0.7, max_tokens=1024):
        call_count[0] += 1
        idx = call_count[0]

        # Odd calls are generation, even calls are quality scoring
        if idx == 1:
            # Initial message generation
            return "SUBJECT: First attempt\nBODY: This is a low quality message."
        elif idx == 2:
            # Quality score for first attempt (low)
            return json.dumps({
                "relevance": 4, "tone": 5, "value_proposition_clarity": 3,
                "cta_effectiveness": 4, "length_appropriateness": 5, "no_hallucinations": 5,
                "improvement_suggestions": ["Needs work"],
            })
        elif idx == 3:
            # Regeneration attempt 1
            return "SUBJECT: Better subject\nBODY: This is a much better personalized message with clear value."
        elif idx == 4:
            # Quality score for regeneration (high)
            return json.dumps({
                "relevance": 8, "tone": 8, "value_proposition_clarity": 8,
                "cta_effectiveness": 8, "length_appropriateness": 8, "no_hallucinations": 9,
                "improvement_suggestions": [],
            })
        return "SUBJECT: Fallback\nBODY: Fallback body"

    mock_llm_client.generate = AsyncMock(side_effect=mock_generate)

    agent = CopywriterAgent(
        llm_client=mock_llm_client,
        settings=mock_settings,
        quality_scorer=quality_scorer,
    )

    lead = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@example.com",
        "company": "Acme",
        "title": "VP Engineering",
        "enrichment_data": {"trigger_events": ["Series B funding"]},
    }
    campaign_context = {
        "sender_name": "Bob",
        "sender_title": "CEO",
        "company_name": "TestCo",
        "value_proposition": "AI-powered outreach",
        "tone_of_voice": "professional",
    }

    result = await agent.write_message(
        lead=lead,
        campaign_context=campaign_context,
        step_type="initial",
        quality_check=True,
    )

    # Should have quality_score in result
    assert "quality_score" in result
    # The best scoring attempt should be chosen
    assert result["quality_score"] >= QUALITY_THRESHOLD
    assert result["subject"] == "Better subject"


@pytest.mark.asyncio
async def test_copywriter_no_quality_check(mock_llm_client, mock_settings):
    """Test copywriter skips quality check when quality_check=False."""
    from agents.copywriter import CopywriterAgent
    from agents.reply_quality import ReplyQualityScorer

    quality_scorer = ReplyQualityScorer(mock_llm_client)
    mock_llm_client.generate = AsyncMock(
        return_value="SUBJECT: Quick subject\nBODY: Quick body content"
    )

    agent = CopywriterAgent(
        llm_client=mock_llm_client,
        settings=mock_settings,
        quality_scorer=quality_scorer,
    )

    lead = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@example.com",
        "company": "Acme",
        "title": "VP",
        "enrichment_data": {},
    }

    result = await agent.write_message(
        lead=lead,
        campaign_context={"company_name": "TestCo", "value_proposition": "AI", "tone_of_voice": "friendly"},
        step_type="initial",
        quality_check=False,
    )

    # Should not have quality_score
    assert "quality_score" not in result
    assert result["subject"] == "Quick subject"
    # LLM should only be called once (for generation only)
    assert mock_llm_client.generate.call_count == 1
