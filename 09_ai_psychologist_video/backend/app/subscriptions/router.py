"""
Подписки: список тарифов, оформление подписки.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.dependencies import get_current_user_id
from app.models.database import (
    async_session_factory,
    User,
    Subscription,
    SubscriptionPlan,
    Transaction,
    TransactionType,
)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

# Описание тарифных планов
PLANS = [
    {
        "id": "free",
        "name": "Free",
        "price": 0,
        "minutes_per_month": 5,
        "description": "5 минут бесплатных консультаций в месяц",
    },
    {
        "id": "basic",
        "name": "Basic",
        "price": 990,
        "minutes_per_month": 60,
        "description": "60 минут консультаций в месяц",
    },
    {
        "id": "premium",
        "name": "Premium",
        "price": 2490,
        "minutes_per_month": -1,  # unlimited
        "description": "Безлимитные консультации",
    },
]


class PlanResponse(BaseModel):
    id: str
    name: str
    price: int
    minutes_per_month: int
    description: str


class SubscribeRequest(BaseModel):
    plan: str


class SubscribeResponse(BaseModel):
    success: bool
    plan: str
    expires_at: str | None = None
    message: str


@router.get("/plans", response_model=list[PlanResponse])
async def get_plans():
    """Список доступных тарифных планов."""
    return [PlanResponse(**p) for p in PLANS]


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(
    request: SubscribeRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Оформление подписки. Проверяет баланс пользователя, списывает стоимость,
    создает/обновляет запись подписки.
    """
    # Проверяем что план существует
    plan_data = next((p for p in PLANS if p["id"] == request.plan), None)
    if not plan_data:
        raise HTTPException(status_code=400, detail="Неизвестный тарифный план")

    try:
        plan_enum = SubscriptionPlan(request.plan)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неизвестный тарифный план")

    async with async_session_factory() as session:
        # Получаем пользователя
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        price = Decimal(str(plan_data["price"]))

        # Для платных планов проверяем баланс
        if price > 0:
            if user.balance < price:
                raise HTTPException(
                    status_code=402,
                    detail="Недостаточно средств для оформления подписки",
                )
            # Списываем стоимость
            user.balance = user.balance - price

            # Создаем транзакцию списания за подписку
            tx = Transaction(
                user_id=user_id,
                amount=price,
                type=TransactionType.debit,
                source=f"subscription:{request.plan}",
            )
            session.add(tx)

        # Устанавливаем срок подписки (30 дней)
        expires_at = datetime.utcnow() + timedelta(days=30)

        # Ищем существующую подписку или создаем новую
        sub_result = await session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        existing_sub = sub_result.scalar_one_or_none()

        if existing_sub:
            existing_sub.plan = plan_enum
            existing_sub.started_at = datetime.utcnow()
            existing_sub.expires_at = expires_at
        else:
            new_sub = Subscription(
                user_id=user_id,
                plan=plan_enum,
                expires_at=expires_at,
            )
            session.add(new_sub)

        await session.commit()

        return SubscribeResponse(
            success=True,
            plan=request.plan,
            expires_at=expires_at.isoformat(),
            message=f"Подписка '{plan_data['name']}' активирована до {expires_at.strftime('%d.%m.%Y')}",
        )
