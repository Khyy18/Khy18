"""
Модуль обработки платежей.

Интеграции:
- Telegram Stars (внутриигровая валюта Telegram, currency=XTR)
- YooKassa (платежная система для РФ)
- Demo topup (для разработки)
"""

import hashlib
import hmac
import logging
import uuid
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.auth.dependencies import get_current_user_id
from app.config import settings
from app.models.database import async_session_factory, User, Transaction, TransactionType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

# Курс конвертации Telegram Stars в рубли (примерный)
STARS_TO_RUB_RATE = Decimal("1.3")


class TopUpRequest(BaseModel):
    amount: Decimal
    source: str = "demo"  # "stars" | "yookassa" | "demo"


class TopUpResponse(BaseModel):
    success: bool
    new_balance: str
    transaction_id: str


class StarsInvoiceRequest(BaseModel):
    stars_amount: int
    description: str = "Пополнение баланса AI Психолог"


class StarsInvoiceResponse(BaseModel):
    invoice_link: str


class YookassaPaymentRequest(BaseModel):
    amount: Decimal
    return_url: str = "https://ai-psychologist.app/payment-success"
    description: str = "Пополнение баланса AI Психолог"


class YookassaPaymentResponse(BaseModel):
    confirmation_url: str
    payment_id: str


@router.post("/create-stars-invoice", response_model=StarsInvoiceResponse)
async def create_stars_invoice(
    request: StarsInvoiceRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Создание invoice для оплаты через Telegram Stars (currency=XTR).
    Вызывает Telegram Bot API createInvoiceLink.
    """
    if not settings.BOT_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="BOT_TOKEN not configured. Stars payments unavailable. Use demo topup.",
        )

    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/createInvoiceLink"
    payload = {
        "title": "Пополнение баланса",
        "description": request.description,
        "payload": f"topup:{user_id}:{request.stars_amount}",
        "currency": "XTR",
        "prices": [
            {"label": "Пополнение баланса", "amount": request.stars_amount}
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            data = response.json()

            if not data.get("ok"):
                logger.error(f"Telegram API error: {data}")
                raise HTTPException(
                    status_code=502, detail="Failed to create invoice link"
                )

            return StarsInvoiceResponse(invoice_link=data["result"])
    except httpx.HTTPError as e:
        logger.error(f"HTTP error creating Stars invoice: {e}")
        raise HTTPException(status_code=502, detail="Telegram API unavailable")


@router.post("/telegram-webhook")
async def telegram_payment_webhook(request: Request):
    """
    Обработка webhook от Telegram для платежей Stars.
    Принимает pre_checkout_query (подтверждение) и successful_payment (зачисление).
    Верифицирует X-Telegram-Bot-Api-Secret-Token заголовок.
    """
    if not settings.BOT_TOKEN:
        raise HTTPException(status_code=503, detail="BOT_TOKEN not configured")

    # Верификация секретного токена Telegram webhook
    expected_secret = settings.TELEGRAM_WEBHOOK_SECRET
    if not expected_secret:
        # Фоллбек: используем SHA256 хеш BOT_TOKEN как секрет
        expected_secret = hashlib.sha256(settings.BOT_TOKEN.encode()).hexdigest()

    received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(received_secret, expected_secret):
        logger.warning("Telegram webhook: invalid secret token")
        raise HTTPException(status_code=403, detail="Invalid secret token")

    body = await request.json()

    # Обработка pre_checkout_query - подтверждаем оплату
    if "pre_checkout_query" in body:
        query = body["pre_checkout_query"]
        query_id = query["id"]

        # Подтверждаем через Bot API
        url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/answerPreCheckoutQuery"
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json={"pre_checkout_query_id": query_id, "ok": True})

        return {"ok": True}

    # Обработка successful_payment - зачисляем средства
    if "message" in body and "successful_payment" in body.get("message", {}):
        message = body["message"]
        payment = message["successful_payment"]
        telegram_id = message["from"]["id"]
        stars_amount = payment["total_amount"]
        invoice_payload = payment.get("invoice_payload", "")

        # Конвертируем Stars в рубли
        rub_amount = Decimal(str(stars_amount)) * STARS_TO_RUB_RATE

        # Начисляем на баланс
        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()

            if user:
                user.balance = user.balance + rub_amount
                tx = Transaction(
                    user_id=user.id,
                    amount=rub_amount,
                    type=TransactionType.deposit,
                    source=f"stars:{stars_amount}",
                )
                session.add(tx)
                await session.commit()
                logger.info(
                    f"Stars payment: user {user.id}, {stars_amount} stars = {rub_amount} rub"
                )
            else:
                logger.warning(f"Stars payment for unknown telegram_id: {telegram_id}")

        return {"ok": True}

    return {"ok": True}


@router.post("/create-yokassa-payment", response_model=YookassaPaymentResponse)
async def create_yokassa_payment(
    request: YookassaPaymentRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Создание платежа через YooKassa API.
    Возвращает URL для подтверждения оплаты.
    """
    if not settings.YOOKASSA_SHOP_ID or not settings.YOOKASSA_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="YooKassa credentials not configured. Use demo topup.",
        )

    payment_id = str(uuid.uuid4())
    url = "https://api.yookassa.ru/v3/payments"
    headers = {
        "Idempotence-Key": payment_id,
        "Content-Type": "application/json",
    }
    payload = {
        "amount": {"value": str(request.amount), "currency": "RUB"},
        "confirmation": {
            "type": "redirect",
            "return_url": request.return_url,
        },
        "capture": True,
        "description": request.description,
        "metadata": {"user_id": user_id},
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
            )
            data = response.json()

            if response.status_code not in (200, 201):
                logger.error(f"YooKassa API error: {data}")
                raise HTTPException(
                    status_code=502, detail="Failed to create YooKassa payment"
                )

            confirmation_url = data.get("confirmation", {}).get("confirmation_url", "")
            return YookassaPaymentResponse(
                confirmation_url=confirmation_url,
                payment_id=data.get("id", payment_id),
            )
    except httpx.HTTPError as e:
        logger.error(f"HTTP error creating YooKassa payment: {e}")
        raise HTTPException(status_code=502, detail="YooKassa API unavailable")


@router.post("/yokassa-webhook")
async def yokassa_webhook(request: Request):
    """
    Webhook от YooKassa: обработка уведомлений о статусе платежа.
    При статусе 'payment.succeeded' зачисляем средства на баланс.

    Безопасность: проверяем IP-адрес отправителя, если YOOKASSA_WEBHOOK_IPS задан.
    В production рекомендуется настроить IP allowlist на уровне nginx/firewall.
    """
    if not settings.YOOKASSA_SHOP_ID:
        raise HTTPException(status_code=503, detail="YooKassa not configured")

    # Проверка IP-адреса отправителя (если настроено)
    if settings.YOOKASSA_WEBHOOK_IPS:
        allowed_ips = [ip.strip() for ip in settings.YOOKASSA_WEBHOOK_IPS.split(",") if ip.strip()]
        client_ip = request.client.host if request.client else ""
        # Учитываем X-Forwarded-For при работе за прокси
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        real_ip = forwarded_for.split(",")[0].strip() if forwarded_for else client_ip
        if allowed_ips and real_ip not in allowed_ips:
            logger.warning(f"YooKassa webhook: rejected IP {real_ip}")
            raise HTTPException(status_code=403, detail="IP not allowed")

    body = await request.json()
    event_type = body.get("event")

    if event_type == "payment.succeeded":
        payment_obj = body.get("object", {})
        amount_value = payment_obj.get("amount", {}).get("value", "0")
        metadata = payment_obj.get("metadata", {})
        user_id = metadata.get("user_id")
        payment_id = payment_obj.get("id", "unknown")

        if not user_id:
            logger.warning(f"YooKassa webhook without user_id in metadata: {payment_id}")
            return {"ok": True}

        rub_amount = Decimal(amount_value)

        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()

            if user:
                user.balance = user.balance + rub_amount
                tx = Transaction(
                    user_id=user.id,
                    amount=rub_amount,
                    type=TransactionType.deposit,
                    source=f"yookassa:{payment_id}",
                )
                session.add(tx)
                await session.commit()
                logger.info(f"YooKassa payment: user {user_id}, {rub_amount} rub")
            else:
                logger.warning(f"YooKassa payment for unknown user: {user_id}")

    return {"ok": True}


@router.post("/topup", response_model=TopUpResponse)
async def topup(request: TopUpRequest, user_id: str = Depends(get_current_user_id)):
    """
    Пополнение баланса пользователя (demo mode).
    В demo-режиме просто начисляет указанную сумму.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
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
