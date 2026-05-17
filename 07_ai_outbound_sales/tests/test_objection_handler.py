"""Tests for ObjectionHandler."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from agents.objection_handler import (
    ExtractedObjection,
    ObjectionHandler,
    ObjectionResponse,
)
from core.models import Call, CallOutcome, CallStatus, Objection
from tests.conftest import make_call, make_lead, make_objection, make_tenant


@pytest.fixture
def handler(mock_llm_client, session_factory, mock_settings):
    """Create an ObjectionHandler instance."""
    return ObjectionHandler(
        llm_client=mock_llm_client,
        session_factory=session_factory,
        settings=mock_settings,
    )


@pytest.fixture
async def seed_objection_data(async_session):
    """Seed database with objection data."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    obj1 = make_objection(
        tenant_id=tenant.id,
        objection_text="It's too expensive for our budget",
        category="pricing",
        responses=[
            {"text": "I understand. Let me show you the ROI.", "success_rate": 0.7, "times_used": 5},
            {"text": "We offer flexible pricing plans.", "success_rate": 0.5, "times_used": 3},
        ],
        times_encountered=8,
    )
    async_session.add(obj1)

    obj2 = make_objection(
        tenant_id=tenant.id,
        objection_text="We need to check with our CTO first",
        category="authority",
        responses=[
            {"text": "I'd be happy to include your CTO in the next meeting.", "success_rate": 0.8, "times_used": 4},
        ],
        times_encountered=4,
    )
    async_session.add(obj2)

    obj3 = make_objection(
        tenant_id=tenant.id,
        objection_text="We already use competitor X",
        category="competitor",
        responses=[],
        times_encountered=2,
    )
    async_session.add(obj3)

    await async_session.commit()
    return {"tenant": tenant, "objections": [obj1, obj2, obj3]}


async def test_extract_objections(handler, mock_llm_client):
    """Test objection extraction from transcript."""
    mock_llm_client.generate = AsyncMock(
        return_value=json.dumps([
            {
                "objection_text": "It's too expensive",
                "category": "pricing",
                "context": "Raised when discussing pricing tier",
            },
            {
                "objection_text": "I need to talk to my manager",
                "category": "authority",
                "context": "End of call when asked about next steps",
            },
        ])
    )

    transcript = "Agent: The price is $500/month. Lead: That's too expensive. Agent: I understand. Lead: Also I need to talk to my manager."
    objections = await handler.extract_objections(transcript)

    assert len(objections) == 2
    assert isinstance(objections[0], ExtractedObjection)
    assert objections[0].category == "pricing"
    assert objections[1].category == "authority"


async def test_extract_objections_empty_transcript(handler):
    """Test extraction with empty transcript."""
    objections = await handler.extract_objections("")
    assert objections == []


async def test_extract_objections_llm_failure(handler, mock_llm_client):
    """Test extraction handles LLM failure gracefully."""
    mock_llm_client.generate = AsyncMock(return_value="not valid json")

    objections = await handler.extract_objections("Some transcript text")
    assert objections == []


async def test_get_best_response(handler, seed_objection_data):
    """Test getting best response for an objection."""
    tenant = seed_objection_data["tenant"]

    response = await handler.get_best_response("expensive budget", tenant.id)

    assert response is not None
    assert isinstance(response, ObjectionResponse)
    assert response.success_rate == 0.7  # Best response from pricing objection


async def test_get_best_response_no_match(handler):
    """Test getting response when no objections exist."""
    response = await handler.get_best_response("some objection", uuid.uuid4())
    assert response is None


async def test_record_objection_outcome(handler, seed_objection_data):
    """Test recording objection outcome updates success rates."""
    objection = seed_objection_data["objections"][0]

    await handler.record_objection_outcome(
        objection_id=objection.id,
        response_used="I understand. Let me show you the ROI.",
        outcome="success",
    )

    # Verify the update (response should have updated success rate)
    from core.models import Objection as ObjModel
    from sqlalchemy import select

    async with handler._session_factory() as session:
        result = await session.execute(
            select(ObjModel).where(ObjModel.id == objection.id)
        )
        updated = result.scalar_one()
        # Original: 0.7 rate with 5 uses, now 6 uses with success
        # New rate = (0.7 * 5 + 1) / 6 = 4.5 / 6 = 0.75
        resp = next(r for r in updated.responses if "ROI" in r["text"])
        assert resp["times_used"] == 6
        assert abs(resp["success_rate"] - 0.75) < 0.01


async def test_record_objection_outcome_new_response(handler, seed_objection_data):
    """Test recording outcome for a new response text."""
    objection = seed_objection_data["objections"][0]

    await handler.record_objection_outcome(
        objection_id=objection.id,
        response_used="A completely new response approach",
        outcome="success",
    )

    from core.models import Objection as ObjModel
    from sqlalchemy import select

    async with handler._session_factory() as session:
        result = await session.execute(
            select(ObjModel).where(ObjModel.id == objection.id)
        )
        updated = result.scalar_one()
        new_resp = next(r for r in updated.responses if "new response" in r["text"])
        assert new_resp["times_used"] == 1
        assert new_resp["success_rate"] == 1.0


async def test_build_library_from_calls(handler, mock_llm_client, async_session):
    """Test batch building the objection library from calls."""
    tenant = make_tenant()
    async_session.add(tenant)
    await async_session.flush()

    # Create a lead for the call
    lead = make_lead(tenant_id=tenant.id)
    async_session.add(lead)
    await async_session.flush()

    # Create a call with transcript
    call = make_call(
        tenant_id=tenant.id,
        lead_id=lead.id,
        status=CallStatus.completed,
        outcome=CallOutcome.not_interested,
        transcript="Agent: Hello! Lead: It's too expensive. Agent: I see.",
    )
    async_session.add(call)
    await async_session.commit()

    mock_llm_client.generate = AsyncMock(
        return_value=json.dumps([
            {
                "objection_text": "It's too expensive",
                "category": "pricing",
                "context": "Early in call",
            }
        ])
    )

    await handler.build_library_from_calls(tenant.id)

    # Verify objection was stored
    from core.models import Objection as ObjModel
    from sqlalchemy import select

    async with handler._session_factory() as session:
        result = await session.execute(
            select(ObjModel).where(ObjModel.tenant_id == tenant.id)
        )
        objections = result.scalars().all()
        assert len(objections) == 1
        assert objections[0].category == "pricing"
        assert objections[0].objection_text == "It's too expensive"
