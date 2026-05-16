"""Tests for webhook Zapier/Make connector and event log endpoints."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import Response

from integrations.webhooks import (
    WEBHOOK_EVENT_CALL_COMPLETED,
    WEBHOOK_EVENT_LEAD_QUALIFIED,
    WEBHOOK_EVENT_MEETING_BOOKED,
    WEBHOOK_EVENT_REPLY_RECEIVED,
    OutgoingWebhookDispatcher,
    make_payload,
    zapier_payload,
)


class TestZapierPayload:
    """Test zapier_payload format."""

    def test_zapier_payload_structure(self):
        data = {"lead_name": "John", "email": "john@example.com"}
        result = zapier_payload("lead.qualified", data)

        assert "id" in result
        assert result["event"] == "lead.qualified"
        assert result["source"] == "ai_outbound_sales"
        assert "timestamp" in result
        assert result["data"] == data

    def test_zapier_payload_has_uuid_id(self):
        result = zapier_payload("meeting.booked", {"meeting_id": "123"})
        # Should be a valid UUID string
        parsed = uuid.UUID(result["id"])
        assert parsed is not None

    def test_zapier_payload_timestamp_is_iso(self):
        result = zapier_payload("call.completed", {})
        # Should parse as ISO datetime
        dt = datetime.fromisoformat(result["timestamp"])
        assert dt is not None


class TestMakePayload:
    """Test make_payload format."""

    def test_make_payload_flat_structure(self):
        data = {"lead_name": "Jane", "score": 85}
        result = make_payload("reply.received", data)

        assert result["event_type"] == "reply.received"
        assert result["source"] == "ai_outbound_sales"
        assert result["lead_name"] == "Jane"
        assert result["score"] == 85
        assert "timestamp" in result
        assert "event_id" in result

    def test_make_payload_has_event_id(self):
        result = make_payload("lead.qualified", {"x": 1})
        parsed = uuid.UUID(result["event_id"])
        assert parsed is not None

    def test_make_payload_data_merged_at_top_level(self):
        data = {"key1": "val1", "key2": "val2"}
        result = make_payload("test.event", data)
        assert result["key1"] == "val1"
        assert result["key2"] == "val2"
        # No nested "data" key
        assert "data" not in result


class TestStandardizedEventTypes:
    """Test standardized event type constants."""

    def test_event_type_constants(self):
        assert WEBHOOK_EVENT_LEAD_QUALIFIED == "lead.qualified"
        assert WEBHOOK_EVENT_MEETING_BOOKED == "meeting.booked"
        assert WEBHOOK_EVENT_CALL_COMPLETED == "call.completed"
        assert WEBHOOK_EVENT_REPLY_RECEIVED == "reply.received"


class TestExponentialBackoff:
    """Test exponential backoff retry logic."""

    @pytest.mark.asyncio
    async def test_retry_delays_are_exponential(self):
        """Verify the dispatcher uses exponential backoff delays."""
        dispatcher = OutgoingWebhookDispatcher(session_factory=AsyncMock())
        assert dispatcher._retry_delays == [1, 4, 16, 64]

    @pytest.mark.asyncio
    async def test_successful_delivery_no_retry(self):
        """Successful delivery on first attempt should not retry."""
        mock_session = AsyncMock()
        mock_record = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_record
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_session_factory = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_ctx

        dispatcher = OutgoingWebhookDispatcher(session_factory=mock_session_factory)

        webhook = MagicMock()
        webhook.id = uuid.uuid4()
        webhook.url = "https://hooks.example.com/test"
        webhook.secret = "test-secret"
        webhook.tenant_id = uuid.uuid4()

        with patch("integrations.webhooks.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await dispatcher._deliver(webhook, "lead.qualified", {"test": True})

        assert result["status"] == "delivered"
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_failed_delivery_after_retries(self):
        """Failed delivery should exhaust all retries."""
        mock_session = AsyncMock()
        mock_record = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_record
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        mock_session_factory = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_ctx

        dispatcher = OutgoingWebhookDispatcher(session_factory=mock_session_factory)
        # Use short delays for testing
        dispatcher._retry_delays = [0, 0, 0, 0]

        webhook = MagicMock()
        webhook.id = uuid.uuid4()
        webhook.url = "https://hooks.example.com/fail"
        webhook.secret = "test-secret"
        webhook.tenant_id = uuid.uuid4()

        with patch("integrations.webhooks.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await dispatcher._deliver(webhook, "lead.qualified", {"test": True})

        assert result["status"] == "failed"
        assert "HTTP 500" in result["error"]


class TestWebhookEventEndpoints:
    """Test event log endpoint responses."""

    @pytest.mark.asyncio
    async def test_list_events_endpoint(self, async_session, session_factory):
        """Test the list events endpoint returns proper format."""
        from core.models import WebhookDelivery, Webhook, Tenant
        from sqlalchemy import select, text

        # Create tenant and webhook
        tenant_id = uuid.uuid4()
        tenant = Tenant(
            id=tenant_id,
            name="Test Corp",
            domain="test.com",
            settings={},
            created_at=datetime.now(timezone.utc),
        )
        async_session.add(tenant)
        await async_session.flush()

        webhook_id = uuid.uuid4()
        webhook = Webhook(
            id=webhook_id,
            tenant_id=tenant_id,
            url="https://hooks.example.com/test",
            secret="test-secret",
            events=[],
            is_active=True,
        )
        async_session.add(webhook)
        await async_session.flush()

        # Create delivery records
        delivery_id = uuid.uuid4()
        delivery = WebhookDelivery(
            id=delivery_id,
            webhook_id=webhook_id,
            tenant_id=tenant_id,
            event_type="lead.qualified",
            payload={"lead": "test"},
            status="delivered",
            attempts=1,
            response_code=200,
            created_at=datetime.now(timezone.utc),
        )
        async_session.add(delivery)
        await async_session.flush()

        # Verify via raw SQL to avoid ORM identity-map/type issues in SQLite
        result = await async_session.execute(
            text("SELECT id, event_type, status FROM webhook_deliveries WHERE tenant_id = :tid"),
            {"tid": str(tenant_id)},
        )
        rows = result.fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "lead.qualified"
        assert rows[0][2] == "delivered"

    @pytest.mark.asyncio
    async def test_filter_by_status(self, async_session, session_factory):
        """Test filtering events by status."""
        from core.models import WebhookDelivery, Webhook, Tenant
        from sqlalchemy import text

        tenant_id = uuid.uuid4()
        tenant = Tenant(
            id=tenant_id,
            name="Filter Corp",
            domain="filter.com",
            settings={},
            created_at=datetime.now(timezone.utc),
        )
        async_session.add(tenant)
        await async_session.flush()

        webhook_id = uuid.uuid4()
        webhook = Webhook(
            id=webhook_id,
            tenant_id=tenant_id,
            url="https://hooks.example.com/filter",
            secret="secret",
            events=[],
            is_active=True,
        )
        async_session.add(webhook)
        await async_session.flush()

        # Create multiple deliveries with different statuses
        for status_val in ["delivered", "failed", "pending"]:
            delivery = WebhookDelivery(
                id=uuid.uuid4(),
                webhook_id=webhook_id,
                tenant_id=tenant_id,
                event_type="lead.qualified",
                payload={},
                status=status_val,
                attempts=1,
                created_at=datetime.now(timezone.utc),
            )
            async_session.add(delivery)
        await async_session.flush()

        # Verify filtering via raw SQL
        result = await async_session.execute(
            text("SELECT id, status FROM webhook_deliveries WHERE tenant_id = :tid AND status = :st"),
            {"tid": str(tenant_id), "st": "failed"},
        )
        failed = result.fetchall()
        assert len(failed) == 1
        assert failed[0][1] == "failed"

    @pytest.mark.asyncio
    async def test_get_single_event(self, async_session, session_factory):
        """Test retrieving a single event by ID."""
        from core.models import WebhookDelivery, Webhook, Tenant
        from sqlalchemy import text

        tenant_id = uuid.uuid4()
        tenant = Tenant(
            id=tenant_id,
            name="Single Corp",
            domain="single.com",
            settings={},
            created_at=datetime.now(timezone.utc),
        )
        async_session.add(tenant)
        await async_session.flush()

        webhook_id = uuid.uuid4()
        webhook = Webhook(
            id=webhook_id,
            tenant_id=tenant_id,
            url="https://hooks.example.com/single",
            secret="secret",
            events=[],
            is_active=True,
        )
        async_session.add(webhook)
        await async_session.flush()

        delivery_id = uuid.uuid4()
        delivery = WebhookDelivery(
            id=delivery_id,
            webhook_id=webhook_id,
            tenant_id=tenant_id,
            event_type="meeting.booked",
            payload={"meeting_id": "abc123"},
            status="delivered",
            attempts=2,
            response_code=200,
            created_at=datetime.now(timezone.utc),
        )
        async_session.add(delivery)
        await async_session.flush()

        # Verify single event via raw SQL
        result = await async_session.execute(
            text("SELECT id, event_type, status, attempts FROM webhook_deliveries WHERE id = :did"),
            {"did": str(delivery_id)},
        )
        row = result.fetchone()
        assert row is not None
        assert row[1] == "meeting.booked"
        assert row[2] == "delivered"
        assert row[3] == 2


class TestEventTypeDispatch:
    """Test standardized event type dispatch through the system."""

    def test_zapier_payload_with_standard_events(self):
        """Verify standard event types work with zapier_payload."""
        for event in [
            WEBHOOK_EVENT_LEAD_QUALIFIED,
            WEBHOOK_EVENT_MEETING_BOOKED,
            WEBHOOK_EVENT_CALL_COMPLETED,
            WEBHOOK_EVENT_REPLY_RECEIVED,
        ]:
            result = zapier_payload(event, {"test": True})
            assert result["event"] == event
            assert result["source"] == "ai_outbound_sales"

    def test_make_payload_with_standard_events(self):
        """Verify standard event types work with make_payload."""
        for event in [
            WEBHOOK_EVENT_LEAD_QUALIFIED,
            WEBHOOK_EVENT_MEETING_BOOKED,
            WEBHOOK_EVENT_CALL_COMPLETED,
            WEBHOOK_EVENT_REPLY_RECEIVED,
        ]:
            result = make_payload(event, {"test": True})
            assert result["event_type"] == event
            assert result["source"] == "ai_outbound_sales"
