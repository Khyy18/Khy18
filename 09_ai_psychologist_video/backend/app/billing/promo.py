"""
Модуль промокодов: применение промокодов, начисление бонусов.
"""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.dependencies import get_current_user_id
from app.models.database import (
    async_session_factory,
    User,
    PromoCode,
    Transaction,
    TransactionType,
)

router = APIRouter(prefix="/billing", tags=["billing"])


class ApplyPromoRequest(BaseModel):
    code: str


class ApplyPromoResponse(BaseModel):
    success: bool
    amount: str
    new_balance: str
    message: str


@router.post("/apply-promo", response_model=ApplyPromoResponse)
async def apply_promo(
    request: ApplyPromoRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Применение промокода: проверяет существование, срок действия, лимит использований.
    При успехе начисляет бонус на баланс и создает транзакцию.
    """
    async with async_session_factory() as session:
        # Ищем промокод в базе
        result = await session.execute(
            select(PromoCode).where(PromoCode.code == request.code)
        )
        promo = result.scalar_one_or_none()

        if not promo:
            raise HTTPException(status_code=404, detail="Промокод не найден")

        # Проверяем срок действия
        if promo.expires_at and promo.expires_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="Промокод истёк")

        # Проверяем лимит использований
        if promo.current_uses >= promo.max_uses:
            raise HTTPException(
                status_code=400, detail="Промокод уже использован максимальное количество раз"
            )

        # Получаем пользователя
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        # Проверяем, не использовал ли пользователь уже этот промокод
        existing_tx = await session.execute(
            select(Transaction).where(
                Transaction.user_id == user_id,
                Transaction.source == f"promo:{promo.code}",
            )
        )
        if existing_tx.scalar_one_or_none():
            raise HTTPException(
                status_code=400, detail="Вы уже использовали этот промокод"
            )

        # Начисляем бонус
        user.balance = user.balance + promo.amount
        promo.current_uses = promo.current_uses + 1

        # Создаем транзакцию
        tx = Transaction(
            user_id=user_id,
            amount=promo.amount,
            type=TransactionType.deposit,
            source=f"promo:{promo.code}",
        )
        session.add(tx)
        await session.commit()
        await session.refresh(user)

        return ApplyPromoResponse(
            success=True,
            amount=str(promo.amount),
            new_balance=str(user.balance),
            message=f"Промокод применён! Начислено {promo.amount} руб.",
        )
