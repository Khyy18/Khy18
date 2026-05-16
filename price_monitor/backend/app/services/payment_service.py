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

    async def create_telegram_stars_payment(
        self,
        user_id: int,
        stars_amount: int,
        db: AsyncSession,
    ) -> dict:
        """Create a Telegram Stars payment. 1 Star = 1 day VIP."""
        payment = Payment(
            user_id=user_id,
            amount=float(stars_amount),
            currency="XTR",  # Telegram Stars currency code
            status="pending",
            plan=f"{stars_amount}_stars",
            provider="telegram_stars",
        )
        db.add(payment)
        await db.commit()
        await db.refresh(payment)
        return {
            "payment_id": payment.id,
            "stars_amount": stars_amount,
            "vip_days": stars_amount,
        }

    async def handle_successful_stars_payment(
        self,
        user_id: int,
        stars_amount: int,
        db: AsyncSession,
        telegram_payment_charge_id: str = "",
    ) -> dict:
        """Process successful Telegram Stars payment - activate VIP.

        IMPORTANT: In production, this method must only be called from the
        Telegram Bot webhook handler after receiving a `successful_payment`
        update. The `telegram_payment_charge_id` from the update serves as
        proof of payment. Never expose this as a public API endpoint without
        verifying the payment through the Telegram Bot API first.
        """
        if not telegram_payment_charge_id:
            return {"ok": False, "error": "Missing payment charge ID"}

        from sqlalchemy import select

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return {"ok": False, "error": "User not found"}

        # Find the pending Stars payment and store the charge ID
        pending_result = await db.execute(
            select(Payment).where(
                Payment.user_id == user_id,
                Payment.provider == "telegram_stars",
                Payment.status == "pending",
            ).order_by(Payment.created_at.desc()).limit(1)
        )
        pending_payment = pending_result.scalar_one_or_none()
        if pending_payment:
            pending_payment.status = "confirmed"
            pending_payment.provider_payment_id = telegram_payment_charge_id

        days = stars_amount  # 1 star = 1 day
        user.is_vip = True
        user.vip_expires_at = datetime.utcnow() + timedelta(days=days)
        await db.commit()
        return {"ok": True, "vip_until": user.vip_expires_at.isoformat()}

payment_service = PaymentService()
