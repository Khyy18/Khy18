"""Telegram Stars payment integration."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.billing import billing_manager
from app.config import settings
from app.http_client import get_http_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])

# Payment packages: stars -> coins
PAYMENT_PACKAGES = {
    50: 100,    # 50 stars = 100 coins
    100: 250,   # 100 stars = 250 coins
    200: 600,   # 200 stars = 600 coins
    500: 1800,  # 500 stars = 1800 coins
}


class CreateInvoiceRequest(BaseModel):
    """Request to create a payment invoice."""

    user_id: str
    stars_amount: int


class CreateInvoiceResponse(BaseModel):
    """Response with invoice URL."""

    invoice_url: str
    stars_amount: int
    coins_amount: int


class PaymentWebhookRequest(BaseModel):
    """Telegram payment webhook data."""

    update_id: int
    pre_checkout_query: Optional[dict] = None
    message: Optional[dict] = None


class PaymentWebhookResponse(BaseModel):
    """Response to payment webhook."""

    ok: bool
    message: str = ""


@router.post("/create-invoice", response_model=CreateInvoiceResponse)
async def create_invoice(request: CreateInvoiceRequest):
    """Create a Telegram Stars invoice for purchasing coins.

    Generates an invoice link using the Telegram Bot API.
    """
    if request.stars_amount not in PAYMENT_PACKAGES:
        available = list(PAYMENT_PACKAGES.keys())
        raise HTTPException(
            status_code=400,
            detail=f"Invalid stars amount. Available packages: {available}",
        )

    if not settings.telegram_bot_token:
        raise HTTPException(
            status_code=503,
            detail="Payment service not configured",
        )

    coins_amount = PAYMENT_PACKAGES[request.stars_amount]
    client = get_http_client()

    try:
        response = await client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/createInvoiceLink",
            json={
                "title": f"{coins_amount} Astro Coins",
                "description": f"Purchase {coins_amount} coins for astrology sessions",
                "payload": f"{request.user_id}:{request.stars_amount}:{coins_amount}",
                "currency": "XTR",
                "prices": [
                    {
                        "label": f"{coins_amount} Astro Coins",
                        "amount": request.stars_amount,
                    }
                ],
            },
        )
        response.raise_for_status()
        result = response.json()

        if not result.get("ok"):
            raise HTTPException(
                status_code=502,
                detail="Failed to create invoice via Telegram API",
            )

        invoice_url = result["result"]
        return CreateInvoiceResponse(
            invoice_url=invoice_url,
            stars_amount=request.stars_amount,
            coins_amount=coins_amount,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create invoice: {e}")
        raise HTTPException(status_code=502, detail="Payment service error")


@router.post("/webhook", response_model=PaymentWebhookResponse)
async def payment_webhook(request: PaymentWebhookRequest):
    """Handle Telegram payment webhooks.

    Processes pre_checkout_query (approve) and successful_payment (credit balance).
    """
    # Handle pre-checkout query (approve the payment)
    if request.pre_checkout_query:
        query = request.pre_checkout_query
        query_id = query.get("id")

        if not query_id:
            return PaymentWebhookResponse(ok=False, message="Missing query ID")

        if settings.telegram_bot_token:
            client = get_http_client()
            try:
                await client.post(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/answerPreCheckoutQuery",
                    json={"pre_checkout_query_id": query_id, "ok": True},
                )
            except Exception as e:
                logger.error(f"Failed to answer pre-checkout query: {e}")

        return PaymentWebhookResponse(ok=True, message="Pre-checkout approved")

    # Handle successful payment
    if request.message and request.message.get("successful_payment"):
        payment = request.message["successful_payment"]
        payload = payment.get("invoice_payload", "")

        try:
            parts = payload.split(":")
            if len(parts) == 3:
                user_id, stars_str, coins_str = parts
                coins_amount = int(coins_str)

                # Credit balance
                if billing_manager.redis:
                    await billing_manager.topup_balance(user_id, coins_amount)
                    logger.info(
                        f"Payment successful: user={user_id}, "
                        f"stars={stars_str}, coins={coins_amount}"
                    )

                return PaymentWebhookResponse(
                    ok=True,
                    message=f"Credited {coins_amount} coins to user {user_id}",
                )
            else:
                logger.error(f"Invalid payment payload format: {payload}")
                return PaymentWebhookResponse(ok=False, message="Invalid payload")
        except (ValueError, IndexError) as e:
            logger.error(f"Error processing payment: {e}")
            return PaymentWebhookResponse(ok=False, message="Payment processing error")

    return PaymentWebhookResponse(ok=True, message="No action required")
