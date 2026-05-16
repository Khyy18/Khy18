"""Outgoing webhook dispatcher with HMAC-SHA256 signing and retry logic."""

import asyncio
import hashlib
import hmac
import json
import logging
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import Webhook

logger = logging.getLogger(__name__)


class OutgoingWebhookDispatcher:
    """Dispatches events to registered webhook URLs with HMAC signing and retry."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self._retry_delays = [1, 2, 4]  # seconds

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
            event_type: The type of event (e.g., 'lead_qualified', 'meeting_booked').
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

        results = []
        for webhook in matching:
            delivery = await self._deliver(webhook, event_type, payload)
            results.append(delivery)

        return results

    async def _deliver(self, webhook: Webhook, event_type: str, payload: dict) -> dict:
        """Deliver payload to a single webhook with retry."""
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

        last_error = None
        for attempt, delay in enumerate(self._retry_delays):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        webhook.url, content=body, headers=headers
                    )
                    if response.status_code < 400:
                        return {
                            "webhook_id": str(webhook.id),
                            "status": "delivered",
                            "status_code": response.status_code,
                        }
                    last_error = f"HTTP {response.status_code}"
            except Exception as exc:
                last_error = str(exc)

            if attempt < len(self._retry_delays) - 1:
                await asyncio.sleep(delay)

        logger.warning(
            "Webhook delivery failed for %s after %d attempts: %s",
            webhook.url,
            len(self._retry_delays),
            last_error,
        )
        return {
            "webhook_id": str(webhook.id),
            "status": "failed",
            "error": last_error,
        }
