"""Tests for agents/edge_cases.py - EdgeCaseDetector."""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.edge_cases import EdgeCaseDetector, EdgeCaseType


@pytest.fixture
def detector() -> EdgeCaseDetector:
    """Create an EdgeCaseDetector with no LLM client."""
    return EdgeCaseDetector(llm_client=None)


@pytest.fixture
def lead_data() -> dict:
    """Sample lead data for testing."""
    return {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@example.com",
        "company": "Acme Inc",
        "title": "VP of Sales",
    }


class TestDetectEdgeCases:
    """Tests for EdgeCaseDetector.detect_edge_case()."""

    def test_detect_language_switch(self, detector: EdgeCaseDetector, lead_data: dict) -> None:
        """Message with non-English content should be detected as language_switch."""
        message = "Bonjour, je voudrais discuter de votre offre."
        result = detector.detect_edge_case(message, lead_data)
        assert result == EdgeCaseType.LANGUAGE_SWITCH

    def test_detect_language_switch_non_ascii(
        self, detector: EdgeCaseDetector, lead_data: dict
    ) -> None:
        """Message with high non-ASCII ratio should be detected as language_switch."""
        message = "\u041f\u0440\u0438\u0432\u0435\u0442, \u043c\u0435\u043d\u044f \u0438\u043d\u0442\u0435\u0440\u0435\u0441\u0443\u0435\u0442 \u0432\u0430\u0448\u0435 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435"
        result = detector.detect_edge_case(message, lead_data)
        assert result == EdgeCaseType.LANGUAGE_SWITCH

    def test_detect_forwarded_reply(self, detector: EdgeCaseDetector, lead_data: dict) -> None:
        """Message with FW: prefix should be detected as forwarded_reply."""
        message = "FW: Original subject\n\nHere's the forwarded content."
        result = detector.detect_edge_case(message, lead_data)
        assert result == EdgeCaseType.FORWARDED_REPLY

    def test_detect_forwarded_reply_fwd(
        self, detector: EdgeCaseDetector, lead_data: dict
    ) -> None:
        """Message with Fwd: prefix should be detected as forwarded_reply."""
        message = "Fwd: Check this out\n---------- Forwarded message ----------"
        result = detector.detect_edge_case(message, lead_data)
        assert result == EdgeCaseType.FORWARDED_REPLY

    def test_detect_delayed_reply(self, detector: EdgeCaseDetector, lead_data: dict) -> None:
        """Conversation with last message 45 days ago should detect delayed_reply."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        conversation_history = [
            {"content": "Initial outreach", "direction": "outbound", "sent_at": old_date},
        ]
        result = detector.detect_edge_case(
            "Hi, sorry for the late reply!", lead_data, conversation_history
        )
        assert result == EdgeCaseType.DELAYED_REPLY

    def test_detect_phone_request(self, detector: EdgeCaseDetector, lead_data: dict) -> None:
        """Message requesting a call should be detected as phone_request."""
        message = "Can you call me at your earliest convenience?"
        result = detector.detect_edge_case(message, lead_data)
        assert result == EdgeCaseType.PHONE_REQUEST

    def test_detect_phone_request_hop_on_call(
        self, detector: EdgeCaseDetector, lead_data: dict
    ) -> None:
        """Message with 'hop on a call' should be detected as phone_request."""
        message = "I'd love to discuss this further. Let's hop on a call."
        result = detector.detect_edge_case(message, lead_data)
        assert result == EdgeCaseType.PHONE_REQUEST

    def test_detect_wrong_person(self, detector: EdgeCaseDetector, lead_data: dict) -> None:
        """Message indicating wrong person should be detected."""
        message = "I'm not the right person for this, you should talk to John Smith in sales."
        result = detector.detect_edge_case(message, lead_data)
        assert result == EdgeCaseType.WRONG_PERSON

    def test_detect_auto_reply_loop(
        self, detector: EdgeCaseDetector, lead_data: dict
    ) -> None:
        """Message with auto-reply signature and history of auto-replies should detect loop."""
        message = "This is an automatic reply. I am currently out of office."
        now = datetime.now(timezone.utc)
        conversation_history = [
            {"content": "This is an automatic reply. I will be back Monday.", "direction": "inbound", "sent_at": (now - timedelta(days=2)).isoformat()},
            {"content": "Follow up message", "direction": "outbound", "sent_at": (now - timedelta(days=1)).isoformat()},
            {"content": "Out of office auto-reply. I am away.", "direction": "inbound", "sent_at": (now - timedelta(hours=12)).isoformat()},
            {"content": "Another automatic reply - currently unavailable", "direction": "inbound", "sent_at": (now - timedelta(hours=6)).isoformat()},
        ]
        result = detector.detect_edge_case(message, lead_data, conversation_history)
        assert result == EdgeCaseType.AUTO_REPLY_LOOP

    def test_detect_multiple_rapid_replies(
        self, detector: EdgeCaseDetector, lead_data: dict
    ) -> None:
        """3+ inbound messages within 5 minutes should detect multiple_rapid_replies."""
        now = datetime.now(timezone.utc)
        conversation_history = [
            {
                "content": "Hey, quick question",
                "direction": "inbound",
                "sent_at": (now - timedelta(minutes=4)).isoformat(),
            },
            {
                "content": "Actually, one more thing",
                "direction": "inbound",
                "sent_at": (now - timedelta(minutes=3)).isoformat(),
            },
            {
                "content": "And also this",
                "direction": "inbound",
                "sent_at": (now - timedelta(minutes=2)).isoformat(),
            },
        ]
        # Use a normal message that doesn't trigger earlier edge cases
        result = detector.detect_edge_case(
            "Got it, thanks", lead_data, conversation_history
        )
        assert result == EdgeCaseType.MULTIPLE_RAPID_REPLIES

    def test_detect_cc_present(self, detector: EdgeCaseDetector, lead_data: dict) -> None:
        """Headers with CC should detect cc_detected."""
        headers = {"cc": "boss@company.com"}
        result = detector.detect_edge_case(
            "Thanks for the info, copying my manager.",
            lead_data,
            headers=headers,
        )
        assert result == EdgeCaseType.CC_DETECTED

    def test_detect_no_edge_case(self, detector: EdgeCaseDetector, lead_data: dict) -> None:
        """Normal business reply should not trigger any edge case."""
        message = "Thanks for reaching out. I am interested in learning more about your product."
        result = detector.detect_edge_case(message, lead_data)
        assert result is None


class TestHandleEdgeCases:
    """Tests for EdgeCaseDetector.handle_edge_case()."""

    async def test_handle_phone_request(
        self, detector: EdgeCaseDetector, lead_data: dict
    ) -> None:
        """Phone request handler should include booking link."""
        campaign_context = {
            "booking_link": "https://calendly.com/test",
            "phone": "+1-555-0100",
        }
        result = await detector.handle_edge_case(
            EdgeCaseType.PHONE_REQUEST,
            "Can you call me?",
            lead_data,
            campaign_context,
        )
        assert result["action"] == "provide_phone"
        assert "calendly.com/test" in result["response_body"]
        assert "+1-555-0100" in result["response_body"]
        assert result["create_new_lead"] is False

    async def test_handle_wrong_person(
        self, detector: EdgeCaseDetector, lead_data: dict
    ) -> None:
        """Wrong person handler should extract referred name and create_new_lead."""
        message = "I'm not the right person, you should talk to Jane Wilson in marketing."
        result = await detector.handle_edge_case(
            EdgeCaseType.WRONG_PERSON,
            message,
            lead_data,
        )
        assert result["action"] == "create_referral"
        assert result["create_new_lead"] is True
        assert result["new_lead_info"] is not None
        assert result["new_lead_info"]["name"] == "Jane Wilson"
        assert result["new_lead_info"]["referred_by"] == "john@example.com"

    async def test_handle_auto_reply_loop(
        self, detector: EdgeCaseDetector, lead_data: dict
    ) -> None:
        """Auto-reply loop handler should return stop_sequence action."""
        result = await detector.handle_edge_case(
            EdgeCaseType.AUTO_REPLY_LOOP,
            "This is an automatic reply",
            lead_data,
        )
        assert result["action"] == "stop_sequence"
        assert result["response_body"] == ""
        assert "Auto-reply loop detected" in result["notes"]
        assert result["create_new_lead"] is False

    async def test_handle_delayed_reply(
        self, detector: EdgeCaseDetector, lead_data: dict
    ) -> None:
        """Delayed reply handler should include context refresh language."""
        campaign_context = {"company_name": "TechCorp"}
        result = await detector.handle_edge_case(
            EdgeCaseType.DELAYED_REPLY,
            "Hi, sorry for the late reply",
            lead_data,
            campaign_context,
        )
        assert result["action"] == "context_refresh"
        assert "been a while" in result["response_body"]
        assert "TechCorp" in result["response_body"]

    async def test_handle_language_switch(
        self, detector: EdgeCaseDetector, lead_data: dict
    ) -> None:
        """Language switch handler should acknowledge language preference."""
        result = await detector.handle_edge_case(
            EdgeCaseType.LANGUAGE_SWITCH,
            "Bonjour, merci pour votre message",
            lead_data,
        )
        assert result["action"] == "respond_in_language"
        assert "different language" in result["response_body"]

    async def test_handle_cc_detected(
        self, detector: EdgeCaseDetector, lead_data: dict
    ) -> None:
        """CC detected handler should adjust tone to formal."""
        result = await detector.handle_edge_case(
            EdgeCaseType.CC_DETECTED,
            "Thanks, copying my team on this.",
            lead_data,
        )
        assert result["action"] == "adjust_tone"
        assert "CC'd" in result["notes"]

    async def test_handle_multiple_rapid_replies(
        self, detector: EdgeCaseDetector, lead_data: dict
    ) -> None:
        """Multiple rapid replies handler should batch response."""
        result = await detector.handle_edge_case(
            EdgeCaseType.MULTIPLE_RAPID_REPLIES,
            "One more thing",
            lead_data,
        )
        assert result["action"] == "batch_response"
        assert "messages" in result["response_body"].lower()


class TestConversationAgentEdgeCaseIntegration:
    """Integration test showing ConversationAgent uses EdgeCaseDetector."""

    async def test_conversation_agent_routes_edge_case(
        self,
        async_session,
        session_factory,
        mock_llm_client,
        mock_settings,
    ) -> None:
        """ConversationAgent should detect edge case before classification."""
        from agents.conversation import ConversationAgent
        from core.models import (
            Campaign,
            CampaignStatus,
            Lead,
            LeadStatus,
            Message,
            MessageDirection,
            MessageStatus,
            Tenant,
        )
        from integrations.calendar import CalendarIntegration

        # Create test data
        tenant_id = uuid.uuid4()
        tenant = Tenant(
            id=tenant_id,
            name="Test Corp",
            domain="testcorp.com",
            settings={},
            created_at=datetime.now(timezone.utc),
        )
        async_session.add(tenant)

        campaign_id = uuid.uuid4()
        campaign = Campaign(
            id=campaign_id,
            tenant_id=tenant_id,
            name="Test Campaign",
            icp_filter={"company_name": "TestCo", "value_proposition": "Test VP"},
            status=CampaignStatus.active,
            created_at=datetime.now(timezone.utc),
        )
        async_session.add(campaign)

        lead_id = uuid.uuid4()
        lead = Lead(
            id=lead_id,
            tenant_id=tenant_id,
            email="prospect@example.com",
            first_name="Jane",
            last_name="Smith",
            company="Their Corp",
            title="Director",
            status=LeadStatus.contacted,
            score=0.5,
            enrichment_data={},
            created_at=datetime.now(timezone.utc),
        )
        async_session.add(lead)

        msg_id = uuid.uuid4()
        message = Message(
            id=msg_id,
            lead_id=lead_id,
            campaign_id=campaign_id,
            channel="email",
            direction=MessageDirection.inbound,
            content="This is an automatic reply. I am out of office until January 15th.",
            subject="Re: Partnership",
            status=MessageStatus.sent,
            sent_at=datetime.now(timezone.utc),
        )
        async_session.add(message)
        await async_session.commit()

        # Setup ConversationAgent
        mock_calendar = AsyncMock(spec=CalendarIntegration)
        mock_calendar.generate_booking_link = AsyncMock(return_value="https://cal.com/test")

        agent = ConversationAgent(
            llm_client=mock_llm_client,
            settings=mock_settings,
            calendar=mock_calendar,
            session_factory=session_factory,
        )

        # Process the auto-reply message
        result = await agent.handle_reply(str(msg_id))

        # Should detect auto-reply edge case and NOT call classify_reply
        assert "edge_case_type" in result
        assert result["edge_case_type"] == EdgeCaseType.AUTO_REPLY_LOOP
        assert result["response"]["action"] == "stop_sequence"
        # LLM should NOT have been called for classification
        mock_llm_client.generate.assert_not_called()
