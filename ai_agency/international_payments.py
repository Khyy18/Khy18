"""Международные платежи: Stripe + Crypto (NOWPayments)."""

import hashlib
import hmac
import json
import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import config
import database

logger = logging.getLogger(__name__)

# Lazy Stripe import
_stripe = None


def _get_stripe():
    """Получить модуль stripe с настроенным ключом."""
    global _stripe
    if _stripe is None:
        try:
            import stripe
            stripe.api_key = config.STRIPE_SECRET_KEY
            _stripe = stripe
        except ImportError:
            logger.warning("stripe package not installed")
            return None
    return _stripe


async def create_stripe_session(
    client_id: int,
    amount_usd: float,
    description: str,
) -> Optional[str]:
    """
    Создать Stripe Checkout Session.
    Возвращает URL чекаута или None при ошибке.
    """
    stripe = _get_stripe()
    if not stripe or not config.STRIPE_SECRET_KEY:
        logger.warning("Stripe not configured")
        return None

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": description},
                        "unit_amount": int(amount_usd * 100),
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            metadata={"client_id": str(client_id)},
            success_url=f"https://t.me/{config.BOT_USERNAME}?start=payment_success",
            cancel_url=f"https://t.me/{config.BOT_USERNAME}?start=payment_cancel",
        )
        return session.url
    except Exception as e:
        logger.error("Ошибка создания Stripe сессии: %s", e)
        return None


async def handle_stripe_webhook(payload: bytes, signature: str) -> Optional[dict]:
    """
    Обработать Stripe webhook.
    Возвращает dict с данными платежа или None.
    """
    stripe = _get_stripe()
    if not stripe or not config.STRIPE_WEBHOOK_SECRET:
        return None

    try:
        event = stripe.Webhook.construct_event(
            payload, signature, config.STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        logger.error("Ошибка верификации Stripe webhook: %s", e)
        return None

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        client_id = int(session.get("metadata", {}).get("client_id", "0"))
        amount_cents = session.get("amount_total", 0)
        amount_usd = amount_cents / 100.0
        # Конвертируем USD -> RUB (примерный курс)
        amount_rub = amount_usd * 90.0

        if client_id:
            # Пополняем баланс
            balance = await database.get_client_balance(client_id)
            await database.update_balance(client_id, balance + amount_rub)
            await database.add_payment(client_id, amount_rub, method="stripe")
            logger.info(
                "Stripe payment: client=%d, usd=%.2f, rub=%.2f",
                client_id, amount_usd, amount_rub,
            )
            return {
                "client_id": client_id,
                "amount_usd": amount_usd,
                "amount_rub": amount_rub,
                "payment_id": session.get("id"),
            }
    return None


async def create_crypto_payment(
    client_id: int,
    amount_usd: float,
    currency: str = "USDT",
) -> Optional[str]:
    """
    Создать крипто-платёж через NOWPayments API.
    Возвращает URL для оплаты или None.
    """
    if not config.NOWPAYMENTS_API_KEY:
        logger.warning("NOWPayments not configured")
        return None

    try:
        import aiohttp
        url = "https://api.nowpayments.io/v1/invoice"
        headers = {
            "x-api-key": config.NOWPAYMENTS_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "price_amount": amount_usd,
            "price_currency": "usd",
            "pay_currency": currency.lower(),
            "order_id": f"client_{client_id}_{int(amount_usd * 100)}",
            "order_description": f"Balance top-up ${amount_usd}",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("invoice_url")
                else:
                    text = await resp.text()
                    logger.error("NOWPayments error: %s", text)
                    return None
    except Exception as e:
        logger.error("Ошибка создания крипто-платежа: %s", e)
        return None


async def handle_crypto_webhook(payload: dict) -> Optional[dict]:
    """
    Обработать NOWPayments IPN webhook.
    Возвращает dict с данными платежа или None.
    """
    if not config.NOWPAYMENTS_IPN_SECRET:
        return None

    # Верификация подписи
    sorted_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    expected_sig = hmac.new(
        config.NOWPAYMENTS_IPN_SECRET.encode(),
        sorted_payload.encode(),
        hashlib.sha512,
    ).hexdigest()

    received_sig = payload.pop("verify_hash", "")
    if not hmac.compare_digest(expected_sig, received_sig):
        logger.warning("NOWPayments IPN signature mismatch")
        return None

    payment_status = payload.get("payment_status")
    if payment_status not in ("finished", "confirmed"):
        return None

    order_id = payload.get("order_id", "")
    # Парсим client_id из order_id формата "client_{id}_{amount}"
    parts = order_id.split("_")
    if len(parts) < 2:
        return None

    try:
        client_id = int(parts[1])
    except (ValueError, IndexError):
        return None

    amount_usd = float(payload.get("price_amount", 0))
    amount_rub = amount_usd * 90.0

    if client_id and amount_rub > 0:
        balance = await database.get_client_balance(client_id)
        await database.update_balance(client_id, balance + amount_rub)
        await database.add_payment(client_id, amount_rub, method="crypto")
        logger.info(
            "Crypto payment: client=%d, usd=%.2f, rub=%.2f",
            client_id, amount_usd, amount_rub,
        )
        return {
            "client_id": client_id,
            "amount_usd": amount_usd,
            "amount_rub": amount_rub,
        }
    return None


def get_payment_methods_keyboard(amount_rub: float) -> InlineKeyboardMarkup:
    """Создать клавиатуру с методами оплаты."""
    amount_usd = amount_rub / 90.0
    keyboard = [
        [InlineKeyboardButton(
            f"\U0001f4b3 YooKassa ({int(amount_rub)} \u20bd)",
            callback_data=f"pay_yookassa:{int(amount_rub)}",
        )],
    ]
    if config.STRIPE_SECRET_KEY:
        keyboard.append([InlineKeyboardButton(
            f"\U0001f4b3 Stripe (${amount_usd:.2f} USD)",
            callback_data=f"pay_stripe:{int(amount_rub)}",
        )])
    if config.NOWPAYMENTS_API_KEY:
        keyboard.append([InlineKeyboardButton(
            f"\U0001f4b0 Crypto USDT (${amount_usd:.2f})",
            callback_data=f"pay_crypto:{int(amount_rub)}",
        )])
    keyboard.append([InlineKeyboardButton(
        "\u2b50 Telegram Stars",
        callback_data=f"topup_stars:100",
    )])
    return InlineKeyboardMarkup(keyboard)
