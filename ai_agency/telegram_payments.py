"""Интеграция нативных платежей Telegram Stars."""

import logging
from typing import Optional

from telegram import Bot, LabeledPrice, Update
from telegram.ext import Application, PreCheckoutQueryHandler, MessageHandler, filters

import config
import database

logger = logging.getLogger(__name__)


async def create_stars_invoice(
    chat_id: int,
    title: str,
    description: str,
    price_stars: int,
    payload: str,
    bot: Optional[Bot] = None,
) -> None:
    """
    Отправить инвойс для оплаты через Telegram Stars.

    provider_token = '' для нативных Stars-платежей.
    """
    if bot is None:
        bot = Bot(token=config.TELEGRAM_BOT_TOKEN)

    prices = [LabeledPrice(label=title, amount=price_stars)]

    await bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        payload=payload,
        provider_token="",  # Telegram Stars
        currency="XTR",  # Stars currency code
        prices=prices,
    )
    logger.info(
        "Stars инвойс отправлен: chat_id=%d, stars=%d, payload=%s",
        chat_id,
        price_stars,
        payload,
    )


async def pre_checkout_handler(update: Update, context) -> None:
    """
    Обработчик pre_checkout_query.

    Подтверждаем все запросы (валидация минимальна для Stars).
    """
    query = update.pre_checkout_query
    await query.answer(ok=True)
    logger.debug("Pre-checkout подтверждён: %s", query.invoice_payload)


async def successful_payment_handler(update: Update, context) -> None:
    """
    Обработчик успешного платежа через Stars.

    Конвертирует Stars в рубли и зачисляет на баланс.
    """
    payment = update.message.successful_payment
    telegram_id = update.effective_user.id
    stars_amount = payment.total_amount
    payload = payment.invoice_payload

    # Конвертация Stars в рубли
    rub_amount = stars_amount * config.STARS_TO_RUB_RATE

    # Зачисляем на баланс
    from billing import top_up_balance

    new_balance = await top_up_balance(telegram_id, rub_amount, method="telegram_stars")

    logger.info(
        "Stars платёж: user=%d, stars=%d, rub=%.2f, new_balance=%.2f, payload=%s",
        telegram_id,
        stars_amount,
        rub_amount,
        new_balance,
        payload,
    )

    await update.message.reply_text(
        f"\u2705 Оплата получена!\n\n"
        f"\u2b50 Stars: {stars_amount}\n"
        f"\U0001f4b0 Зачислено: {rub_amount:.0f} \u20bd\n"
        f"\U0001f4b3 Баланс: {new_balance:.0f} \u20bd"
    )


def register_payment_handlers(application: Application) -> None:
    """Зарегистрировать обработчики платежей в Application."""
    application.add_handler(
        PreCheckoutQueryHandler(pre_checkout_handler)
    )
    application.add_handler(
        MessageHandler(
            filters.SUCCESSFUL_PAYMENT,
            successful_payment_handler,
        )
    )
    logger.info("Обработчики Telegram Stars платежей зарегистрированы")
