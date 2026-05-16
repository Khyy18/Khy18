"""YuKassa payment integration service."""

import uuid
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Payment, User

YUKASSA_API_URL = "https://api.yookassa.ru/v3/payments"

PLAN_PRICES = {
    "monthly": 299.0,
    "yearly": 2490.0,
}


class PaymentService:
    """Service for YuKassa payment processing."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _generate_idempotency_key(self) -> str:
        """Generate a unique idempotency key for the request."""
        return str(uuid.uuid4())

    async def create_payment(
        self, user_id: int, plan: str, amount: float | None = None
    ) -> dict:
        """Create a payment via YuKassa API.

        Returns dict with confirmation_url and payment_id.
        """
        if amount is None:
            amount = PLAN_PRICES.get(plan, 299.0)

        idempotency_key = self._generate_idempotency_key()

        payload = {
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "confirmation": {
                "type": "redirect",
                "return_url": "https://app.pricemonitor.ru/payment/success",
            },
            "capture": True,
            "description": f"VIP подписка ({plan})",
            "metadata": {"user_id": str(user_id), "plan": plan},
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                YUKASSA_API_URL,
                json=payload,
                auth=(settings.yukassa_shop_id, settings.yukassa_secret_key),
                headers={"Idempotence-Key": idempotency_key},
                timeout=10.0,
            )

        if response.status_code in (200, 201):
            data = response.json()
            provider_payment_id = data.get("id", "")
            confirmation_url = (
                data.get("confirmation", {}).get("confirmation_url", "")
            )

            payment = Payment(
                user_id=user_id,
                amount=amount,
                currency="RUB",
                status="pending",
                provider="yukassa",
                provider_payment_id=provider_payment_id,
            )
            self.db.add(payment)
            await self.db.commit()

            return {
                "confirmation_url": confirmation_url,
                "payment_id": provider_payment_id,
            }

        return {"confirmation_url": "", "payment_id": ""}

    async def handle_webhook(self, payload: dict) -> bool:
        """Handle YuKassa webhook notification.

        Activates VIP if payment succeeded.
        Returns True if processed successfully.
        """
        event = payload.get("event", "")
        payment_obj = payload.get("object", {})
        payment_id = payment_obj.get("id", "")
        status = payment_obj.get("status", "")

        if event != "payment.succeeded" or status != "succeeded":
            return False

        result = await self.db.execute(
            select(Payment).where(Payment.provider_payment_id == payment_id)
        )
        payment = result.scalar_one_or_none()
        if not payment:
            return False

        payment.status = "succeeded"

        user_result = await self.db.execute(
            select(User).where(User.id == payment.user_id)
        )
        user = user_result.scalar_one_or_none()
        if user:
            user.is_vip = True
            user.vip_expires_at = datetime.utcnow() + timedelta(days=30)

        await self.db.commit()
        return True
