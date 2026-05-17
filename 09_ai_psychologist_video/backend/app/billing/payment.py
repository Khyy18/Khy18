"""
Модуль обработки платежей.

Содержит стабы для интеграции с:
- Telegram Stars (внутриигровая валюта Telegram)
- YooKassa (платежная система для РФ)
"""

from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.models.database import async_session_factory, User, Transaction, TransactionType

router = APIRouter(prefix="/billing", tags=["billing"])


class TopUpRequest(BaseModel):
    user_id: str
    amount: Decimal
    source: str = "demo"  # "stars" | "yookassa" | "demo"


class TopUpResponse(BaseModel):
    success: bool
    new_balance: str
    transaction_id: str


async def process_stars_payment(user_id: str, stars_amount: int) -> bool:
    """
    Обработка платежа через Telegram Stars.

    TODO: Интеграция с Telegram Bot Payments API
    -----------------------------------------------
    1. Получаем pre_checkout_query от Telegram
    2. Подтверждаем через answer_pre_checkout_query
    3. Получаем successful_payment в сообщении
    4. Конвертируем Stars в рубли (1 Star ~ 1.3 RUB, курс плавающий)
    5. Начисляем на баланс пользователя

    Telegram Stars API:
    - Создаем invoice через createInvoiceLink с currency="XTR"
    - prices = [LabeledPrice(label="Пополнение баланса", amount=stars_amount)]
    - После оплаты получаем telegram_payment_charge_id для рефандов
    """
    # Стаб: в реальности здесь проверка через Telegram Bot API
    return True


async def process_yookassa_payment(user_id: str, amount_rub: Decimal) -> dict:
    """
    Обработка платежа через YooKassa.

    TODO: Интеграция с YooKassa API (https://yookassa.ru/developers)
    -----------------------------------------------------------------
    1. Создаем Payment через yookassa SDK:
       payment = Payment.create({
           "amount": {"value": str(amount_rub), "currency": "RUB"},
           "confirmation": {"type": "redirect", "return_url": "..."},
           "capture": True,
           "description": "Пополнение баланса AI Психолог"
       })
    2. Редиректим пользователя на confirmation.confirmation_url
    3. Получаем webhook notification о статусе платежа
    4. При статусе "succeeded" начисляем на баланс

    Настройки:
    - YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY в переменных окружения
    - Webhook URL регистрируется в личном кабинете YooKassa
    - Тестовый режим: используем тестовые ключи из ЛК
    """
    # Стаб: возвращаем mock confirmation URL
    return {
        "payment_id": "mock_payment_id",
        "confirmation_url": "https://yookassa.ru/mock-payment",
        "status": "pending",
    }


@router.post("/topup", response_model=TopUpResponse)
async def topup(request: TopUpRequest):
    """
    Пополнение баланса пользователя.
    В demo-режиме просто начисляет указанную сумму.
    В production будет вызывать process_stars_payment или process_yookassa_payment.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.id == request.user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Начисляем на баланс
        user.balance = user.balance + request.amount

        # Создаем транзакцию
        tx = Transaction(
            user_id=user.id,
            amount=request.amount,
            type=TransactionType.deposit,
            source=request.source,
        )
        session.add(tx)
        await session.commit()
        await session.refresh(user)
        await session.refresh(tx)

        return TopUpResponse(
            success=True,
            new_balance=str(user.balance),
            transaction_id=tx.id,
        )
