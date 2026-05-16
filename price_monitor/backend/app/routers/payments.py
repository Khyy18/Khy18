"""Payments router - Telegram Stars + YuKassa payments."""
from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.schemas.payments import PaymentConfirm, PaymentCreate, PaymentOut, TelegramStarsPayment
from app.services.payment_service import payment_service

router = APIRouter(prefix="/payments", tags=["payments"])

PLANS = {
    "month": {"amount": 299.0, "stars": 150, "days": 30},
    "quarter": {"amount": 699.0, "stars": 350, "days": 90},
    "year": {"amount": 1999.0, "stars": 1000, "days": 365},
}

@router.get("", response_model=list[PaymentOut])
async def get_payments(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get payment history for the current user."""

    result = await db.execute(
        select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc())
    )
    payments = result.scalars().all()
    return [
        PaymentOut(
            id=p.id,
            amount=p.amount,
            currency=p.currency,
            status=p.status,
            plan=p.plan,
            provider=p.provider,
            created_at=p.created_at.isoformat(),
        )
        for p in payments
    ]

@router.post("/yukassa")
async def create_yukassa_payment(
    data: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a YuKassa payment."""
    if data.plan not in PLANS:
        raise HTTPException(status_code=400, detail="Неизвестный тарифный план")

    plan_info = PLANS[data.plan]
    result = await payment_service.create_yukassa_payment(
        user_id=user.id,
        amount=plan_info["amount"],
        plan=data.plan,
        db=db,
    )
    return result

@router.post("/telegram-stars")
async def create_stars_payment(
    data: TelegramStarsPayment,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a Telegram Stars payment."""
    if data.plan not in PLANS:
        raise HTTPException(status_code=400, detail="Неизвестный тарифный план")

    payment = Payment(
        user_id=user.id,
        amount=float(data.stars_amount),
        currency="XTR",
        status="pending",
        plan=data.plan,
        provider="telegram_stars",
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return {"payment_id": payment.id, "stars_amount": data.stars_amount}

@router.post("/confirm")
async def confirm_payment(
    data: PaymentConfirm,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Confirm a payment and activate VIP."""
    result = await payment_service.confirm_payment(
        user=user,
        provider_payment_id=data.provider_payment_id,
        db=db,
    )
    return result
