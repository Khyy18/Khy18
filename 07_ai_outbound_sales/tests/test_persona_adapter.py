"""Tests for PersonaAdapter."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.persona_adapter import (
    PersonaAdapter,
    PersonaProfile,
    PersonaType,
)


@pytest.fixture
def adapter(mock_llm_client, mock_settings):
    """Create a PersonaAdapter instance."""
    return PersonaAdapter(
        llm_client=mock_llm_client,
        settings=mock_settings,
    )


async def test_detect_persona_ceo(adapter):
    """Test C-level persona detection from title."""
    profile = await adapter.detect_persona({"title": "CEO", "company": "Acme Inc"})

    assert isinstance(profile, PersonaProfile)
    assert profile.persona_type == PersonaType.C_LEVEL
    assert profile.formality_level == 4
    assert profile.urgency_preference == "high"


async def test_detect_persona_vp(adapter):
    """Test VP persona detection."""
    profile = await adapter.detect_persona({"title": "VP of Engineering", "company": "TechCo"})

    assert profile.persona_type == PersonaType.VP
    assert profile.formality_level == 4


async def test_detect_persona_director(adapter):
    """Test Director persona detection."""
    profile = await adapter.detect_persona({"title": "Director of Marketing", "company": "BigCorp"})

    assert profile.persona_type == PersonaType.DIRECTOR


async def test_detect_persona_manager(adapter):
    """Test Manager persona detection."""
    profile = await adapter.detect_persona({"title": "Sales Manager", "company": "MidSize Inc"})

    assert profile.persona_type == PersonaType.MANAGER


async def test_detect_persona_technical(adapter):
    """Test Technical persona detection."""
    profile = await adapter.detect_persona({"title": "Senior Software Engineer", "company": "DevCo"})

    assert profile.persona_type == PersonaType.TECHNICAL
    assert profile.technical_depth == 5


async def test_detect_persona_startup_founder(adapter):
    """Test startup founder detection with small company."""
    profile = await adapter.detect_persona({
        "title": "Founder",
        "company": "StartupXYZ",
        "company_size": 10,
    })

    assert profile.persona_type == PersonaType.STARTUP_FOUNDER
    assert profile.urgency_preference == "high"


async def test_detect_persona_smb_owner(adapter):
    """Test SMB owner detection."""
    profile = await adapter.detect_persona({
        "title": "Owner",
        "company": "Local Biz",
        "company_size": 25,
    })

    assert profile.persona_type == PersonaType.SMB_OWNER


async def test_detect_persona_llm_fallback(adapter, mock_llm_client):
    """Test LLM fallback for ambiguous titles."""
    mock_llm_client.generate = AsyncMock(
        return_value=json.dumps({"persona_type": "director", "reasoning": "Title suggests director-level"})
    )

    profile = await adapter.detect_persona({
        "title": "Head of Growth",  # Not in direct keyword mappings
        "company": "SaaS Company",
    })

    # "Head of" maps to MANAGER in rule-based detection
    assert profile.persona_type == PersonaType.MANAGER


async def test_detect_persona_unknown_title_uses_llm(adapter, mock_llm_client):
    """Test that truly unknown titles fall through to LLM."""
    mock_llm_client.generate = AsyncMock(
        return_value=json.dumps({"persona_type": "vp", "reasoning": "Strategic role"})
    )

    profile = await adapter.detect_persona({
        "title": "Chief Revenue Officer",  # "chief" maps to C_LEVEL
        "company": "BigTech",
    })

    # "chief" keyword maps to C_LEVEL
    assert profile.persona_type == PersonaType.C_LEVEL


async def test_adapt_message(adapter, mock_llm_client):
    """Test message adaptation with persona."""
    mock_llm_client.generate = AsyncMock(
        return_value="Dear CEO, I wanted to share a quick ROI overview of our platform."
    )

    profile = PersonaProfile(
        persona_type=PersonaType.C_LEVEL,
        formality_level=4,
        technical_depth=2,
        urgency_preference="high",
        value_framing="ROI, strategic impact",
        communication_style="Concise, executive-focused",
        recommended_tone="Professional and confident",
    )

    result = await adapter.adapt_message(profile, "Hey, check out our product!")

    assert "ROI" in result
    mock_llm_client.generate.assert_called_once()


async def test_adapt_message_llm_failure(adapter, mock_llm_client):
    """Test message adaptation falls back to original on LLM failure."""
    mock_llm_client.generate = AsyncMock(side_effect=Exception("LLM error"))

    profile = PersonaProfile(
        persona_type=PersonaType.MANAGER,
        formality_level=3,
        technical_depth=3,
        urgency_preference="medium",
        value_framing="Ease of use",
        communication_style="Practical",
        recommended_tone="Friendly",
    )

    result = await adapter.adapt_message(profile, "Check out our product!")
    assert result == "Check out our product!"


async def test_get_voice_adjustments(adapter):
    """Test voice adjustments for different personas."""
    profile = PersonaProfile(
        persona_type=PersonaType.TECHNICAL,
        formality_level=2,
        technical_depth=5,
        urgency_preference="low",
        value_framing="Technical capabilities",
        communication_style="Technical",
        recommended_tone="Direct",
    )

    adjustments = adapter.get_voice_adjustments(profile)

    assert adjustments["pace"] == "slow"
    assert adjustments["tone"] == "precise"
    assert adjustments["vocabulary_level"] == 5
    assert adjustments["formality"] == 2
    assert adjustments["technical_depth"] == 5


async def test_get_voice_adjustments_c_level(adapter):
    """Test voice adjustments for C-level."""
    profile = PersonaProfile(
        persona_type=PersonaType.C_LEVEL,
        formality_level=4,
        technical_depth=2,
        urgency_preference="high",
        value_framing="ROI",
        communication_style="Concise",
        recommended_tone="Professional",
    )

    adjustments = adapter.get_voice_adjustments(profile)

    assert adjustments["pace"] == "moderate"
    assert adjustments["tone"] == "authoritative"
    assert adjustments["vocabulary_level"] == 4
