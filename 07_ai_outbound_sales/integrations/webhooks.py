"""Outgoing webhook dispatcher with HMAC-SHA256 signing and retry logic."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import random
import uuid as _uuid_mod
from datetime import datetime, timezone
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import Webhook, WebhookDelivery

logger = logging.getLogger(__name__)


# ---------- Standardized Event Types ----------

WEBHOOK_EVENT_LEAD_QUALIFIED = "lead.qualified"
WEBHOOK_EVENT_MEETING_BOOKED = "meeting.booked"
WEBHOOK_EVENT_CALL_COMPLETED = "call.completed"
WEBHOOK_EVENT_REPLY_RECEIVED = "reply.received"


# ---------- CRM Payload Templates ----------


def hubspot_contact_payload(
    lead_data: dict,
    conversation_history: list,
    score: float,
    channel: str,
) -> dict:
    """Format payload according to HubSpot contact creation API."""
    notes = "; ".join(
        entry.get("message", "") for entry in conversation_history
    ) if conversation_history else ""
    return {
        "properties": {
            "email": lead_data.get("email", ""),
            "firstname": lead_data.get("first_name", ""),
            "lastname": lead_data.get("last_name", ""),
            "company": lead_data.get("company", ""),
            "jobtitle": lead_data.get("title", ""),
            "lead_score": score,
            "lead_source": "ai_outbound",
            "last_channel": channel,
            "conversation_notes": notes,
        }
    }


def amocrm_contact_payload(
    lead_data: dict,
    conversation_history: list,
    score: float,
    channel: str,
) -> dict:
    """Format payload according to AmoCRM contact creation API."""
    first_name = lead_data.get("first_name", "")
    last_name = lead_data.get("last_name", "")
    name = f"{first_name} {last_name}".strip()
    return {
        "name": name,
        "custom_fields_values": [
            {"field_code": "EMAIL", "values": [{"value": lead_data.get("email", "")}]},
            {"field_code": "COMPANY", "values": [{"value": lead_data.get("company", "")}]},
            {"field_code": "POSITION", "values": [{"value": lead_data.get("title", "")}]},
            {"field_code": "LEAD_SCORE", "values": [{"value": score}]},
        ],
        "_embedded": {
            "tags": [
                {"name": "ai_outbound"},
                {"name": channel},
            ]
        },
    }


def zapier_payload(event_type: str, data: dict) -> dict:
    """Format payload for Zapier webhook triggers.

    Wraps data with id, event, timestamp, and source at the top level.
    """
    return {
        "id": str(_uuid_mod.uuid4()),
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "ai_outbound_sales",
        "data": data,
    }


def make_payload(event_type: str, data: dict) -> dict:
    """Format payload for Make.com (Integromat) webhook triggers.

    Uses flat structure expected by Make.com webhooks.
    """
    flat: dict = {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "ai_outbound_sales",
        "event_id": str(_uuid_mod.uuid4()),
    }
    # Flatten data into the top-level payload
    for key, value in data.items():
        flat[key] = value
    return flat


def format_webhook_payload(
    webhook: "Webhook",
    lead_data: dict,
    conversation_history: list,
    score: float,
    channel: str,
) -> dict:
    """Dispatch to the appropriate template based on webhook.template_type."""
    if webhook.template_type == "hubspot":
        return hubspot_contact_payload(lead_data, conversation_history, score, channel)
    elif webhook.template_type == "amocrm":
        return amocrm_contact_payload(lead_data, conversation_history, score, channel)
    elif webhook.template_type == "zapier":
        data = {
            "lead": lead_data,
            "conversation_history": conversation_history,
            "score": score,
            "channel": channel,
        }
        return zapier_payload("lead.event", data)
    elif webhook.template_type == "make":
        data = {
            "lead": lead_data,
            "conversation_history": conversation_history,
            "score": score,
            "channel": channel,
        }
        return make_payload("lead.event", data)
    # Generic payload
    return {
        "lead": lead_data,
        "conversation_history": conversation_history,
        "score": score,
        "channel": channel,
    }


class OutgoingWebhookDispatcher:
    """Dispatches events to registered webhook URLs with HMAC signing and retry."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        # Exponential backoff delays: 1s, 4s, 16s, 64s max
        self._retry_delays = [1, 4, 16, 64]

    def _sign_payload(self, payload: str, secret: str) -> str:
        """Generate HMAC-SHA256 signature for the payload."""
        return hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def sign_payload(payload: str, secret: str) -> str:
        """Generate HMAC-SHA256 signature for the payload (static version)."""
        return hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def dispatch(
        self, event_type: str, payload: dict, tenant_id: UUID
    ) -> list[dict]:
        """Send POST to registered webhook URLs for the given event type.

        Args:
            event_type: The type of event (e.g., 'lead.qualified', 'meeting.booked').
            payload: The event payload to send.
            tenant_id: The tenant whose webhooks to trigger.

        Returns:
            List of delivery results with webhook_id, status, and any error.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(Webhook).where(
                    Webhook.tenant_id == tenant_id,
                    Webhook.is_active == True,
                )
            )
            webhooks = list(result.scalars().all())

        # Filter webhooks that subscribe to this event type
        matching = [
            w for w in webhooks
            if not w.events or event_type in w.events
        ]

        # Dispatch deliveries concurrently to avoid blocking on failing webhooks
        if not matching:
            return []

        tasks = [
            self._deliver(webhook, event_type, payload, tenant_id)
            for webhook in matching
        ]
        results = await asyncio.gather(*tasks)

        return list(results)

    async def _deliver(
        self,
        webhook: Webhook,
        event_type: str,
        payload: dict,
        tenant_id: UUID | None = None,
    ) -> dict:
        """Deliver payload to a single webhook with exponential backoff and jitter.

        Records each attempt in a WebhookDelivery model.
        """
        body = json.dumps({"event": event_type, "data": payload})
        signature = hmac.new(
            webhook.secret.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Event": event_type,
        }

        # Create WebhookDelivery record
        delivery_id = _uuid_mod.uuid4()
        effective_tenant_id = tenant_id or webhook.tenant_id

        async with self._session_factory() as session:
            delivery_record = WebhookDelivery(
                id=delivery_id,
                webhook_id=webhook.id,
                tenant_id=effective_tenant_id,
                event_type=event_type,
                payload=payload,
                status="pending",
                attempts=0,
            )
            session.add(delivery_record)
            await session.commit()

        last_error = None
        response_code = None

        for attempt in range(len(self._retry_delays)):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        webhook.url, content=body, headers=headers
                    )
                    response_code = response.status_code

                    # Update delivery record
                    async with self._session_factory() as session:
                        result = await session.execute(
                            select(WebhookDelivery).where(
                                WebhookDelivery.id == delivery_id
                            )
                        )
                        record = result.scalar_one_or_none()
                        if record:
                            record.attempts = attempt + 1
                            record.last_attempt_at = datetime.now(timezone.utc)
                            record.response_code = response_code
                            if response.status_code < 400:
                                record.status = "delivered"
                            await session.commit()

                    if response.status_code < 400:
                        return {
                            "webhook_id": str(webhook.id),
                            "delivery_id": str(delivery_id),
                            "status": "delivered",
                            "status_code": response.status_code,
                        }
                    last_error = f"HTTP {response.status_code}"
            except Exception as exc:
                last_error = str(exc)

                # Update attempt count on failure
                async with self._session_factory() as session:
                    result = await session.execute(
                        select(WebhookDelivery).where(
                            WebhookDelivery.id == delivery_id
                        )
                    )
                    record = result.scalar_one_or_none()
                    if record:
                        record.attempts = attempt + 1
                        record.last_attempt_at = datetime.now(timezone.utc)
                        await session.commit()

            if attempt < len(self._retry_delays) - 1:
                # Exponential backoff with jitter
                delay = self._retry_delays[attempt]
                jitter = random.uniform(0, delay * 0.5)
                await asyncio.sleep(delay + jitter)

        # Mark as failed after all retries exhausted
        async with self._session_factory() as session:
            result = await session.execute(
                select(WebhookDelivery).where(WebhookDelivery.id == delivery_id)
            )
            record = result.scalar_one_or_none()
            if record:
                record.status = "failed"
                record.response_code = response_code
                await session.commit()

        logger.warning(
            "Webhook delivery failed for %s after %d attempts: %s",
            webhook.url,
            len(self._retry_delays),
            last_error,
        )
        return {
            "webhook_id": str(webhook.id),
            "delivery_id": str(delivery_id),
            "status": "failed",
            "error": last_error,
        }
