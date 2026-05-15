"""Платёжный шлюз YooKassa: создание платежей, обработка вебхуков."""

import hashlib
import hmac
import logging
import uuid
from typing import Optional

from aiohttp import web
from yookassa import Configuration, Payment as YooPayment

import config
import billing
import database

logger = logging.getLogger(__name__)

# Инициализация YooKassa SDK
Configuration.account_id = config.YOOKASSA_SHOP_ID
Configuration.secret_key = config.YOOKASSA_SECRET_KEY


async def create_payment(
    client_id: int,
    amount: float,
    description: str,
) -> Optional[str]:
    """
    Создать платёж через YooKassa.

    Возвращает URL для оплаты или None при ошибке.
    """
    try:
        payment = YooPayment.create({
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB",
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{config.BOT_USERNAME}",
            },
            "capture": True,
            "description": description,
            "metadata": {
                "client_id": str(client_id),
                "type": "top_up",
            },
        }, uuid.uuid4().hex)

        return payment.confirmation.confirmation_url
    except Exception as e:
        logger.error("Ошибка создания платежа YooKassa: %s", str(e))
        return None


async def create_subscription_payment(
    client_id: int,
    tier: str,
    amount: float,
) -> Optional[str]:
    """
    Создать платёж подписки через YooKassa.

    Возвращает URL для оплаты или None при ошибке.
    """
    try:
        payment = YooPayment.create({
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB",
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{config.BOT_USERNAME}",
            },
            "capture": True,
            "description": f"Подписка {tier.upper()}",
            "metadata": {
                "client_id": str(client_id),
                "type": "subscription",
                "tier": tier,
            },
        }, uuid.uuid4().hex)

        return payment.confirmation.confirmation_url
    except Exception as e:
        logger.error("Ошибка создания платежа подписки: %s", str(e))
        return None


def _verify_webhook_signature(body_bytes: bytes, signature: str) -> bool:
    """
    Проверить HMAC-подпись вебхука YooKassa.

    Подпись передается в заголовке и вычисляется как
    HMAC-SHA256 от тела запроса с YOOKASSA_WEBHOOK_SECRET в качестве ключа.
    """
    if not config.YOOKASSA_WEBHOOK_SECRET:
        logger.warning("YOOKASSA_WEBHOOK_SECRET не задан, верификация подписи невозможна")
        return False
    expected = hmac.new(
        config.YOOKASSA_WEBHOOK_SECRET.encode(),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


async def handle_webhook(request: web.Request) -> web.Response:
    """Обработчик вебхука YooKassa с верификацией подписи и идемпотентностью."""
    # Верификация подписи запроса
    body_bytes = await request.read()
    signature = request.headers.get("HTTP-Notification", "")
    if not signature:
        signature = request.headers.get("Content-Hmac", "")
    if config.YOOKASSA_WEBHOOK_SECRET:
        if not _verify_webhook_signature(body_bytes, signature):
            logger.warning("Невалидная подпись вебхука, запрос отклонён")
            return web.Response(status=403, text="Forbidden")

    try:
        import json
        body = json.loads(body_bytes)
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    event_type = body.get("event")
    if event_type != "payment.succeeded":
        return web.Response(status=200, text="OK")

    payment_obj = body.get("object", {})
    status = payment_obj.get("status")
    if status != "succeeded":
        return web.Response(status=200, text="OK")

    # Проверка идемпотентности: пропускаем уже обработанные платежи
    payment_id = payment_obj.get("id", "")
    if payment_id:
        already_processed = await database.is_payment_processed(payment_id)
        if already_processed:
            logger.info("Дубликат вебхука, payment_id=%s уже обработан", payment_id)
            return web.Response(status=200, text="OK")

    metadata = payment_obj.get("metadata", {})
    client_id_str = metadata.get("client_id")
    if not client_id_str:
        logger.warning("Вебхук без client_id в metadata")
        return web.Response(status=200, text="OK")

    client_id = int(client_id_str)
    amount_value = float(payment_obj.get("amount", {}).get("value", "0"))
    payment_type = metadata.get("type", "top_up")

    if payment_type == "top_up":
        await billing.top_up_balance(client_id, amount_value, method="yookassa")
        logger.info("Пополнение баланса: клиент=%d, сумма=%.2f", client_id, amount_value)
    elif payment_type == "subscription":
        tier = metadata.get("tier", "basic")
        import subscriptions
        await subscriptions.activate_subscription(
            client_id, tier, yookassa_sub_id=payment_obj.get("id")
        )
        logger.info("Подписка активирована: клиент=%d, тариф=%s", client_id, tier)

    # Отмечаем платёж как обработанный
    if payment_id:
        await database.mark_payment_processed(payment_id)

    return web.Response(status=200, text="OK")


def create_webhook_app() -> web.Application:
    """Создать aiohttp-приложение для вебхуков."""
    app = web.Application()
    app.router.add_post("/webhook/yookassa", handle_webhook)
    return app


async def start_webhook_server() -> None:
    """Запустить сервер вебхуков на отдельном порту."""
    app = create_webhook_app()
    port = config.WEB_PORT + 1
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.WEB_HOST, port)
    await site.start()
    logger.info("Webhook-сервер запущен на %s:%d", config.WEB_HOST, port)
