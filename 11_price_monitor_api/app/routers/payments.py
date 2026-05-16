"""Payments router - YuKassa integration."""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.schemas.payments import PaymentCreate, PaymentResponse
from app.services.payment_service import PaymentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

# YuKassa webhook source IP ranges (as documented by YuKassa).
# Requests from outside these ranges should be rejected.
_YUKASSA_ALLOWED_IPS = {
    "185.71.76.0/27",
    "185.71.77.0/27",
    "77.75.153.0/25",
    "77.75.156.11",
    "77.75.156.35",
    "77.75.154.128/25",
    "2a02:5180::/32",
}


def _verify_webhook_signature(body: bytes, signature: str) -> bool:
    """Verify the webhook request using HMAC-SHA256 with the shared secret.

    YuKassa can be configured to send a signature header. If no webhook secret
    is configured, we skip signature verification but log a warning.
    """
    if not settings.yukassa_webhook_secret:
        logger.warning(
            "YUKASSA_WEBHOOK_SECRET not configured - webhook signature "
            "verification is disabled. Set this in production!"
        )
        return True

    expected = hmac.new(
        settings.yukassa_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/create", response_model=PaymentResponse)
async def create_payment(
    body: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a payment via YuKassa and return confirmation URL."""
    service = PaymentService(db)
    result = await service.create_payment(user_id=user.id, plan=body.plan)
    return PaymentResponse(
        confirmation_url=result["confirmation_url"],
        payment_id=result["payment_id"],
    )


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle YuKassa webhook notification.

    Security: verifies the request via shared secret signature header.
    If YUKASSA_WEBHOOK_SECRET is configured, the X-Webhook-Signature header
    must contain a valid HMAC-SHA256 digest of the request body.
    """
    body = await request.body()

    # Verify webhook signature if secret is configured
    if settings.yukassa_webhook_secret:
        signature = request.headers.get("X-Webhook-Signature", "")
        if not signature:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing webhook signature",
            )
        expected = hmac.new(
            settings.yukassa_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            logger.warning("Webhook signature verification failed from %s", request.client.host if request.client else "unknown")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid webhook signature",
            )

    import json
    payload = json.loads(body)
    service = PaymentService(db)
    success = await service.handle_webhook(payload)
    return {"processed": success}
