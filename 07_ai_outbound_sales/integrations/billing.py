from __future__ import annotations
import asyncio
import logging
from typing import Any

import stripe

logger = logging.getLogger(__name__)


class StripeClient:
    """Wrapper around the Stripe Python SDK with async support.

    Uses per-call api_key parameter instead of setting stripe.api_key globally.
    """

    def __init__(self, secret_key: str) -> None:
        self._secret_key = secret_key

    async def create_customer(
        self, email: str, name: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a Stripe customer."""
        try:
            customer = await asyncio.to_thread(
                stripe.Customer.create,
                email=email,
                name=name,
                metadata=metadata,
                api_key=self._secret_key,
            )
            return dict(customer)
        except stripe.StripeError as e:
            logger.warning("Stripe create_customer failed: %s", e)
            return {"error": str(e)}

    async def create_subscription(
        self, customer_id: str, price_id: str
    ) -> dict[str, Any]:
        """Create a subscription for a customer."""
        try:
            subscription = await asyncio.to_thread(
                stripe.Subscription.create,
                customer=customer_id,
                items=[{"price": price_id}],
                api_key=self._secret_key,
            )
            return dict(subscription)
        except stripe.StripeError as e:
            logger.warning("Stripe create_subscription failed: %s", e)
            return {"error": str(e)}

    async def cancel_subscription(
        self, subscription_id: str
    ) -> dict[str, Any]:
        """Cancel an existing subscription."""
        try:
            subscription = await asyncio.to_thread(
                stripe.Subscription.cancel,
                subscription_id,
                api_key=self._secret_key,
            )
            return dict(subscription)
        except stripe.StripeError as e:
            logger.warning("Stripe cancel_subscription failed: %s", e)
            return {"error": str(e)}

    async def change_subscription_plan(
        self, subscription_id: str, new_price_id: str
    ) -> dict[str, Any]:
        """Change a subscription to a different plan."""
        try:
            subscription = await asyncio.to_thread(
                stripe.Subscription.retrieve,
                subscription_id,
                api_key=self._secret_key,
            )
            item_id = subscription["items"]["data"][0]["id"]
            updated = await asyncio.to_thread(
                stripe.Subscription.modify,
                subscription_id,
                items=[{"id": item_id, "price": new_price_id}],
                api_key=self._secret_key,
            )
            return dict(updated)
        except stripe.StripeError as e:
            logger.warning("Stripe change_subscription_plan failed: %s", e)
            return {"error": str(e)}

    async def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> dict[str, Any]:
        """Create a Stripe Checkout Session."""
        try:
            session = await asyncio.to_thread(
                stripe.checkout.Session.create,
                customer=customer_id,
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                api_key=self._secret_key,
            )
            return dict(session)
        except stripe.StripeError as e:
            logger.warning("Stripe create_checkout_session failed: %s", e)
            return {"error": str(e)}

    async def get_invoices(
        self, customer_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get invoices for a customer."""
        try:
            invoices = await asyncio.to_thread(
                stripe.Invoice.list,
                customer=customer_id,
                limit=limit,
                api_key=self._secret_key,
            )
            return [dict(inv) for inv in invoices.data]
        except stripe.StripeError as e:
            logger.warning("Stripe get_invoices failed: %s", e)
            return []

    async def construct_webhook_event(
        self, payload: bytes, sig_header: str, webhook_secret: str
    ) -> dict[str, Any]:
        """Construct and verify a webhook event from Stripe."""
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
            return dict(event)
        except (stripe.SignatureVerificationError, ValueError) as e:
            logger.warning("Stripe webhook verification failed: %s", e)
            return {"error": str(e)}
