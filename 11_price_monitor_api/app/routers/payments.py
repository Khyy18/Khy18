"""Payments router - YuKassa integration."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.schemas.payments import PaymentCreate, PaymentResponse
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["payments"])


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
    """Handle YuKassa webhook notification (no auth required)."""
    payload = await request.json()
    service = PaymentService(db)
    success = await service.handle_webhook(payload)
    return {"processed": success}
