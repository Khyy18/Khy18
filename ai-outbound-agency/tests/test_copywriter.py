"""Tests for the CopywriterAgent."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.copywriter import CopywriterAgent, SEQUENCE_STEPS


@pytest.fixture
def copywriter(mock_llm_client, mock_settings):
    """Create a CopywriterAgent with mocked dependencies."""
    return CopywriterAgent(llm_client=mock_llm_client, settings=mock_settings)


@pytest.fixture
def sample_lead():
    return {
        "first_name": "Jane",
        "last_name": "Smith",
        "email": "jane@acme.com",
        "title": "CTO",
        "company": "Acme Inc",
        "enrichment_data": {
            "trigger_events": ["Series B funding announced"],
            "talking_points": ["Expanding engineering team"],
            "company_news": ["Opened new office in London"],
            "recent_activity": "Spoke at PyCon 2024",
        },
    }


@pytest.fixture
def campaign_context():
    return {
        "sender_name": "Alice Johnson",
        "sender_title": "Account Executive",
        "company_name": "SalesBot AI",
        "value_proposition": "AI-powered outbound that books 3x more meetings",
        "tone_of_voice": "professional and friendly",
    }


async def test_write_message_initial(copywriter, sample_lead, campaign_context, mock_llm_client):
    """Test generating an initial outreach message."""
    mock_llm_client.generate.return_value = "SUBJECT: Quick question about Acme\nBODY: Hi Jane, saw your Series B news."

    result = await copywriter.write_message(sample_lead, campaign_context, "initial")

    assert result["step_type"] == "initial"
    assert result["subject"] == "Quick question about Acme"
    assert result["body"] == "Hi Jane, saw your Series B news."
    mock_llm_client.generate.assert_called_once()


async def test_write_message_follow_up_1(copywriter, sample_lead, campaign_context, mock_llm_client):
    """Test generating a follow_up_1 message."""
    mock_llm_client.generate.return_value = "SUBJECT: One more thing\nBODY: Hey Jane, wanted to share a quick stat."

    result = await copywriter.write_message(sample_lead, campaign_context, "follow_up_1")

    assert result["step_type"] == "follow_up_1"
    assert result["subject"] == "One more thing"
    assert "quick stat" in result["body"]


async def test_write_message_follow_up_2(copywriter, sample_lead, campaign_context, mock_llm_client):
    """Test generating a follow_up_2 message."""
    mock_llm_client.generate.return_value = "SUBJECT: Similar results at TechCo\nBODY: Jane, a company like Acme saw 40% more meetings."

    result = await copywriter.write_message(sample_lead, campaign_context, "follow_up_2")

    assert result["step_type"] == "follow_up_2"
    assert result["subject"] == "Similar results at TechCo"


async def test_write_message_breakup(copywriter, sample_lead, campaign_context, mock_llm_client):
    """Test generating a breakup message."""
    mock_llm_client.generate.return_value = "SUBJECT: Jane\nBODY: No worries if the timing isn't right."

    result = await copywriter.write_message(sample_lead, campaign_context, "breakup")

    assert result["step_type"] == "breakup"
    assert result["subject"] == "Jane"


async def test_write_message_invalid_step_type(copywriter, sample_lead, campaign_context):
    """Test that invalid step_type raises ValueError."""
    with pytest.raises(ValueError, match="Invalid step_type"):
        await copywriter.write_message(sample_lead, campaign_context, "invalid_step")


async def test_parse_response_standard_format(copywriter):
    """Test _parse_response with standard SUBJECT:/BODY: format."""
    response = "SUBJECT: Hello World\nBODY: This is the email body.\nSecond line."
    subject, body = copywriter._parse_response(response)

    assert subject == "Hello World"
    assert body == "This is the email body.\nSecond line."


async def test_parse_response_fallback(copywriter):
    """Test _parse_response falls back when format is not followed."""
    response = "Just a subject\nAnd this is the body text."
    subject, body = copywriter._parse_response(response)

    assert subject == "Just a subject"
    assert body == "And this is the body text."


async def test_write_sequence_returns_4_messages(copywriter, sample_lead, campaign_context, mock_llm_client):
    """Test write_sequence returns 4 messages (one per step)."""
    mock_llm_client.generate.return_value = "SUBJECT: Test\nBODY: Content"

    messages = await copywriter.write_sequence(sample_lead, campaign_context)

    assert len(messages) == 4
    assert [m["step_type"] for m in messages] == SEQUENCE_STEPS
    assert mock_llm_client.generate.call_count == 4


async def test_write_message_llm_failure(copywriter, sample_lead, campaign_context, mock_llm_client):
    """Test that LLM failure results in empty subject and body."""
    mock_llm_client.generate.side_effect = RuntimeError("LLM unavailable")

    result = await copywriter.write_message(sample_lead, campaign_context, "initial")

    assert result["subject"] == ""
    assert result["body"] == ""
    assert result["step_type"] == "initial"
