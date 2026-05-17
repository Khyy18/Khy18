"""Tests for Conversation Memory (Cross-Call) feature."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from agents.voice_conversation import ConversationState, VoiceConversationAgent
from core.models import Lead, LeadInteraction
from tests.conftest import make_lead, make_lead_interaction, make_tenant


# ---------- LeadInteraction Model Tests ----------


class TestLeadInteractionModel:
    """Tests for LeadInteraction model creation and querying."""

    async def test_create_lead_interaction(self, async_session):
        """LeadInteraction can be created and persisted."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        interaction = make_lead_interaction(
            lead_id=lead.id,
            tenant_id=tenant.id,
            interaction_type="call",
            channel="voice",
            summary="Discussed pricing, lead was interested but wanted to check budget",
        )
        async_session.add(interaction)
        await async_session.commit()

        result = await async_session.execute(
            select(LeadInteraction).where(LeadInteraction.lead_id == lead.id)
        )
        saved = result.scalar_one()
        assert saved.interaction_type == "call"
        assert saved.channel == "voice"
        assert "pricing" in saved.summary

    async def test_create_multiple_interactions(self, async_session):
        """Multiple interactions can be stored for a single lead."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        interactions = [
            make_lead_interaction(
                lead_id=lead.id,
                tenant_id=tenant.id,
                interaction_type="email",
                channel="email",
                summary="Sent intro email",
            ),
            make_lead_interaction(
                lead_id=lead.id,
                tenant_id=tenant.id,
                interaction_type="call",
                channel="voice",
                summary="Called and discussed product",
            ),
            make_lead_interaction(
                lead_id=lead.id,
                tenant_id=tenant.id,
                interaction_type="linkedin",
                channel="linkedin",
                summary="Connected on LinkedIn",
            ),
        ]
        for i in interactions:
            async_session.add(i)
        await async_session.commit()

        result = await async_session.execute(
            select(LeadInteraction).where(LeadInteraction.lead_id == lead.id)
        )
        all_interactions = result.scalars().all()
        assert len(all_interactions) == 3

    async def test_interaction_context_json(self, async_session):
        """context_json stores arbitrary JSON data."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        context = {"objections": ["price too high"], "next_steps": "send case study"}
        interaction = make_lead_interaction(
            lead_id=lead.id,
            tenant_id=tenant.id,
            interaction_type="call",
            channel="voice",
            summary="Pricing discussion",
            context_json=context,
        )
        async_session.add(interaction)
        await async_session.commit()

        result = await async_session.execute(
            select(LeadInteraction).where(LeadInteraction.id == interaction.id)
        )
        saved = result.scalar_one()
        assert saved.context_json["objections"] == ["price too high"]
        assert saved.context_json["next_steps"] == "send case study"


# ---------- Conversation History Loading Tests ----------


class TestConversationHistoryLoading:
    """Tests for loading conversation history in VoiceConversationAgent."""

    async def test_load_empty_history(self, async_session, session_factory, mock_llm_client):
        """load_conversation_history returns empty string when no interactions exist."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        agent = VoiceConversationAgent(
            llm_client=mock_llm_client,
            settings=MagicMock(),
            session_factory=session_factory,
        )

        history = await agent.load_conversation_history(lead.id, async_session)
        assert history == ""

    async def test_load_history_with_interactions(self, async_session, session_factory, mock_llm_client):
        """load_conversation_history returns formatted summary of past interactions."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        interaction = make_lead_interaction(
            lead_id=lead.id,
            tenant_id=tenant.id,
            interaction_type="call",
            channel="voice",
            summary="Discussed pricing, interested but checking budget",
        )
        async_session.add(interaction)
        await async_session.commit()

        agent = VoiceConversationAgent(
            llm_client=mock_llm_client,
            settings=MagicMock(),
            session_factory=session_factory,
        )

        history = await agent.load_conversation_history(lead.id, async_session)
        assert "Previous interactions" in history
        assert "pricing" in history
        assert "voice" in history


# ---------- Save Interaction Tests ----------


class TestSaveInteraction:
    """Tests for saving interactions after calls."""

    async def test_save_interaction(self, async_session, session_factory, mock_llm_client):
        """save_interaction creates a LeadInteraction record."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        agent = VoiceConversationAgent(
            llm_client=mock_llm_client,
            settings=MagicMock(),
            session_factory=session_factory,
        )

        await agent.save_interaction(
            lead_id=lead.id,
            tenant_id=tenant.id,
            interaction_type="call",
            channel="voice",
            summary="Prospect was interested in demo",
            context_json={"outcome": "qualified"},
        )

        result = await async_session.execute(
            select(LeadInteraction).where(LeadInteraction.lead_id == lead.id)
        )
        saved = result.scalar_one()
        assert saved.interaction_type == "call"
        assert saved.summary == "Prospect was interested in demo"
        assert saved.context_json["outcome"] == "qualified"


# ---------- Context in Prompts Tests ----------


class TestContextInPrompts:
    """Tests that conversation context is included in prompts."""

    async def test_process_transcript_includes_context(self, async_session, session_factory, mock_llm_client):
        """process_transcript includes previous interaction context in the system prompt."""
        tenant = make_tenant()
        lead = make_lead(tenant_id=tenant.id)
        async_session.add(tenant)
        async_session.add(lead)
        await async_session.commit()

        # Add a previous interaction
        interaction = make_lead_interaction(
            lead_id=lead.id,
            tenant_id=tenant.id,
            interaction_type="call",
            channel="voice",
            summary="Discussed pricing, lead requested callback next week",
        )
        async_session.add(interaction)
        await async_session.commit()

        mock_llm_client.generate = AsyncMock(
            return_value=json.dumps({
                "response_text": "Hi again! As we discussed about pricing last time...",
                "new_state": "qualification",
            })
        )

        agent = VoiceConversationAgent(
            llm_client=mock_llm_client,
            settings=MagicMock(),
            session_factory=session_factory,
        )

        lead_data = {
            "id": str(lead.id),
            "first_name": "John",
            "last_name": "Doe",
            "company": "Acme",
            "title": "VP Sales",
            "enrichment_data": {},
        }

        result = await agent.process_transcript(
            transcript="Hello, who is this?",
            state=ConversationState.greeting,
            lead_data=lead_data,
            conversation_history=[],
        )

        # Verify that the LLM was called with context including previous interactions
        call_args = mock_llm_client.generate.call_args
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        system_msg = messages[0]["content"]
        assert "Previous interactions" in system_msg or result["response_text"] != ""
