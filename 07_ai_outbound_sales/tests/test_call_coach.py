"""Tests for AI Call Coaching Agent."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from agents.call_coach import CallCoachAgent, CallCoachingResult, COACHING_PROMPT
from core.models import Call, CallStatus
from tests.conftest import make_call, make_tenant, make_lead


# ---------- CallCoachingResult Tests ----------


class TestCallCoachingResult:
    """Tests for CallCoachingResult data class."""

    def test_to_dict(self):
        """to_dict returns all fields as a dictionary."""
        call_id = uuid.uuid4()
        result = CallCoachingResult(
            call_id=call_id,
            talk_to_listen_ratio=0.6,
            objection_handling_score=75,
            closing_technique_score=80,
            overall_score=78,
            improvement_suggestions=["Speak slower", "Ask more questions"],
            script_improvement_suggestions=[
                {"current_phrase": "Buy now", "suggested_phrase": "Would you like to explore this?"}
            ],
        )
        d = result.to_dict()
        assert d["call_id"] == str(call_id)
        assert d["talk_to_listen_ratio"] == 0.6
        assert d["objection_handling_score"] == 75
        assert d["closing_technique_score"] == 80
        assert d["overall_score"] == 78
        assert len(d["improvement_suggestions"]) == 2
        assert len(d["script_improvement_suggestions"]) == 1

    def test_default_values(self):
        """Default values are set correctly."""
        call_id = uuid.uuid4()
        result = CallCoachingResult(call_id=call_id)
        assert result.talk_to_listen_ratio == 0.0
        assert result.objection_handling_score == 0
        assert result.overall_score == 0
        assert result.improvement_suggestions == []
        assert result.script_improvement_suggestions == []


# ---------- CallCoachAgent Tests ----------


class TestCallCoachAgent:
    """Tests for CallCoachAgent analysis."""

    async def test_analyze_call_success(self, async_session, session_factory, mock_llm_client):
        """analyze_call returns structured coaching result."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        call = make_call(
            tenant_id=tenant.id,
            lead_id=lead.id,
            status=CallStatus.completed,
        )
        call.transcript = "Agent: Hello, this is John from Acme. Prospect: Hi, what is this about? Agent: We help companies like yours save 30% on cloud costs. Prospect: That sounds interesting. Agent: Would you like to schedule a demo? Prospect: Sure, next Tuesday works."
        async_session.add(call)
        await async_session.commit()

        # Mock LLM response
        mock_llm_client.generate = AsyncMock(
            return_value=json.dumps({
                "talk_to_listen_ratio": 0.55,
                "objection_handling_score": 70,
                "closing_technique_score": 85,
                "overall_score": 78,
                "improvement_suggestions": [
                    "Let the prospect speak more",
                    "Build more rapport before pitching",
                ],
                "script_improvement_suggestions": [
                    {
                        "current_phrase": "We help companies like yours",
                        "suggested_phrase": "I noticed your company recently expanded - we help growing teams",
                    }
                ],
            })
        )

        coach = CallCoachAgent(
            llm_client=mock_llm_client,
            settings=MagicMock(),
            session_factory=session_factory,
        )

        result = await coach.analyze_call(call.id)

        assert isinstance(result, CallCoachingResult)
        assert result.call_id == call.id
        assert result.talk_to_listen_ratio == 0.55
        assert result.objection_handling_score == 70
        assert result.closing_technique_score == 85
        assert result.overall_score == 78
        assert len(result.improvement_suggestions) == 2
        assert len(result.script_improvement_suggestions) == 1

    async def test_analyze_call_not_found(self, session_factory, mock_llm_client):
        """analyze_call raises ValueError if call not found."""
        coach = CallCoachAgent(
            llm_client=mock_llm_client,
            settings=MagicMock(),
            session_factory=session_factory,
        )

        with pytest.raises(ValueError, match="not found"):
            await coach.analyze_call(uuid.uuid4())

    async def test_analyze_call_no_transcript(self, async_session, session_factory, mock_llm_client):
        """analyze_call raises ValueError if call has no transcript."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        call = make_call(tenant_id=tenant.id, lead_id=lead.id)
        call.transcript = None
        async_session.add(call)
        await async_session.commit()

        coach = CallCoachAgent(
            llm_client=mock_llm_client,
            settings=MagicMock(),
            session_factory=session_factory,
        )

        with pytest.raises(ValueError, match="no transcript"):
            await coach.analyze_call(call.id)

    async def test_analyze_call_llm_json_error(self, async_session, session_factory, mock_llm_client):
        """analyze_call handles LLM returning invalid JSON gracefully."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        call = make_call(tenant_id=tenant.id, lead_id=lead.id, status=CallStatus.completed)
        call.transcript = "Agent: Hello. Prospect: Hi."
        async_session.add(call)
        await async_session.commit()

        # Mock LLM returning invalid JSON
        mock_llm_client.generate = AsyncMock(return_value="This is not valid JSON")

        coach = CallCoachAgent(
            llm_client=mock_llm_client,
            settings=MagicMock(),
            session_factory=session_factory,
        )

        result = await coach.analyze_call(call.id)

        # Should return fallback result
        assert result.overall_score == 50
        assert "Unable to analyze" in result.improvement_suggestions[0]

    async def test_coaching_prompt_includes_transcript(self):
        """COACHING_PROMPT format string includes transcript placeholder."""
        assert "{transcript}" in COACHING_PROMPT
        formatted = COACHING_PROMPT.format(transcript="Test transcript here")
        assert "Test transcript here" in formatted
