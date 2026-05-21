"""Tests for ScriptOptimizerAgent."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.script_optimizer import (
    OptimizationSuggestion,
    ScriptAnalysis,
    ScriptOptimizerAgent,
)
from core.models import Call, CallOutcome, CallScript, CallStatus
from tests.conftest import make_call, make_call_script, make_lead, make_tenant


@pytest.fixture
def optimizer(mock_llm_client, session_factory, mock_settings):
    """Create a ScriptOptimizerAgent instance."""
    return ScriptOptimizerAgent(
        llm_client=mock_llm_client,
        session_factory=session_factory,
        settings=mock_settings,
    )


@pytest.fixture
async def seed_script_data(async_session):
    """Seed database with script and calls for testing."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    script = make_call_script(tenant_id=tenant.id)
    async_session.add(script)
    await async_session.flush()

    # Create a lead for calls
    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)
    await async_session.flush()

    # Create successful calls
    for i in range(3):
        call = make_call(
            tenant_id=tenant.id,
            lead_id=lead.id,
            script_id=script.id,
            status=CallStatus.completed,
            outcome=CallOutcome.qualified,
            transcript=f"Agent: Hello! Lead: Hi, tell me more. Agent: Great, let me explain... Lead: Sounds good, schedule a demo. Call {i}",
        )
        async_session.add(call)

    # Create unsuccessful calls
    for i in range(2):
        call = make_call(
            tenant_id=tenant.id,
            lead_id=lead.id,
            script_id=script.id,
            status=CallStatus.completed,
            outcome=CallOutcome.not_interested,
            transcript=f"Agent: Hello! Lead: Not interested right now. Agent: I understand... Call {i}",
        )
        async_session.add(call)

    await async_session.commit()
    return {"tenant": tenant, "script": script, "lead": lead}


async def test_analyze_script_performance(optimizer, seed_script_data, mock_llm_client):
    """Test script performance analysis with mocked calls/transcripts."""
    script = seed_script_data["script"]

    mock_llm_client.generate = AsyncMock(
        return_value=json.dumps({
            "top_performing_phrases": ["let me explain", "schedule a demo"],
            "underperforming_phrases": ["not interested"],
        })
    )

    analysis = await optimizer.analyze_script_performance(script.id)

    assert isinstance(analysis, ScriptAnalysis)
    assert analysis.total_calls == 5
    assert analysis.success_rate == 3.0 / 5.0
    assert len(analysis.top_performing_phrases) == 2
    assert len(analysis.underperforming_phrases) == 1


async def test_analyze_script_no_calls(optimizer):
    """Test analysis with no calls for a script."""
    analysis = await optimizer.analyze_script_performance(uuid.uuid4())

    assert analysis.total_calls == 0
    assert analysis.success_rate == 0.0


async def test_get_optimization_suggestions(optimizer, seed_script_data, mock_llm_client):
    """Test optimization suggestions generation."""
    script = seed_script_data["script"]

    # Mock LLM responses: first for analysis, then for suggestions
    mock_llm_client.generate = AsyncMock(
        side_effect=[
            json.dumps({
                "top_performing_phrases": ["let me explain"],
                "underperforming_phrases": ["not interested"],
            }),
            json.dumps([
                {
                    "section": "greeting",
                    "current_approach": "Generic hello",
                    "suggested_approach": "Personalized greeting with name",
                    "expected_improvement": 0.15,
                    "confidence": 0.7,
                    "supporting_evidence": "Personalized greetings had 15% higher engagement",
                }
            ]),
        ]
    )

    suggestions = await optimizer.get_optimization_suggestions(script.id)

    assert len(suggestions) == 1
    assert isinstance(suggestions[0], OptimizationSuggestion)
    assert suggestions[0].section == "greeting"
    assert suggestions[0].expected_improvement == 0.15
    assert suggestions[0].confidence == 0.7


async def test_create_ab_test_variant(optimizer, seed_script_data, mock_llm_client):
    """Test A/B variant creation from a suggestion."""
    script = seed_script_data["script"]

    mock_llm_client.generate = AsyncMock(
        side_effect=[
            json.dumps({
                "top_performing_phrases": ["let me explain"],
                "underperforming_phrases": ["not interested"],
            }),
            json.dumps([
                {
                    "section": "greeting",
                    "current_approach": "Generic hello",
                    "suggested_approach": "Personalized greeting",
                    "expected_improvement": 0.15,
                    "confidence": 0.7,
                    "supporting_evidence": "Data shows improvement",
                }
            ]),
        ]
    )

    variant_id = await optimizer.create_ab_test_variant(script.id, 0)

    assert isinstance(variant_id, uuid.UUID)


async def test_get_suggestions_script_not_found(optimizer, mock_llm_client):
    """Test suggestions for non-existent script."""
    mock_llm_client.generate = AsyncMock(
        return_value=json.dumps({
            "top_performing_phrases": [],
            "underperforming_phrases": [],
        })
    )

    suggestions = await optimizer.get_optimization_suggestions(uuid.uuid4())
    assert suggestions == []
