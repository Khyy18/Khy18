"""Payment service - YuKassa + Telegram Stars integration."""
from __future__ import annotations


import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Payment, User

logger = logging.getLogger(__name__)

PLAN_DAYS = {
    "month": 30,
    "quarter": 90,
    "year": 365,
}

class PaymentService:
    """Handles YuKassa and Telegram Stars payment processing."""

    async def create_yukassa_payment(
        self,
        user_id: int,
        amount: float,
        plan: str,
        db: AsyncSession,
    ) -> dict:
        """Create a payment via YuKassa API."""
        payment = Payment(
            user_id=user_id,
            amount=amount,
            currency="RUB",
            status="pending",
            plan=plan,
            provider="yukassa",
        )
        db.add(payment)
        await db.commit()
        await db.refresh(payment)

        # Call YuKassa API
        confirmation_url = None
        if settings.yukassa_shop_id and settings.yukassa_secret_key:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        "https://api.yookassa.ru/v3/payments",
                        auth=(settings.yukassa_shop_id, settings.yukassa_secret_key),
                        json={
                            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
                            "confirmation": {
                                "type": "redirect",
                                "return_url": "https://t.me/price_monitor_bot",
                            },
                            "capture": True,
                            "description": f"VIP подписка ({plan})",
                            "metadata": {"payment_id": payment.id},
                        },
                        headers={"Idempotence-Key": str(payment.id)},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        payment.provider_payment_id = data.get("id")
                        await db.commit()
                        confirmation_url = data.get("confirmation", {}).get(
                            "confirmation_url"
                        )
            except Exception as e:
                logger.error("YuKassa API error: %s", e)

        return {
            "payment_id": payment.id,
            "confirmation_url": confirmation_url,
            "amount": amount,
        }

    async def confirm_payment(
        self,
        user: User,
        provider_payment_id: str,
        db: AsyncSession,
    ) -> dict:
        """Confirm payment and activate VIP subscription."""
        from sqlalchemy import select

        result = await db.execute(
            select(Payment).where(
                Payment.user_id == user.id,
                Payment.provider_payment_id == provider_payment_id,
                Payment.status == "pending",
            )
        )
        payment = result.scalar_one_or_none()
        if not payment:
            return {"ok": False, "error": "Платеж не найден"}

        payment.status = "confirmed"
        days = PLAN_DAYS.get(payment.plan, 30)
        user.is_vip = True
        user.vip_expires_at = datetime.utcnow() + timedelta(days=days)

        await db.commit()
        return {"ok": True, "vip_until": user.vip_expires_at.isoformat()}

payment_service = PaymentService()
