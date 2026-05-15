"""Планировщик фоновых задач AI-агентства: retention, upsell, подписки."""

import asyncio
import logging

from telegram import Bot

import config
import database
import subscriptions

logger = logging.getLogger(__name__)


async def retention_check(bot: Bot) -> None:
    """
    Задача удержания: каждые 24ч проверяет клиентов,
    неактивных 7+ дней, и отправляет напоминание.
    """
    while True:
        try:
            inactive_clients = await database.get_clients_inactive_days(7)
            for client in inactive_clients:
                telegram_id = client["telegram_id"]
                name = client.get("first_name") or "друг"
                text = (
                    f"\U0001f44b {name}, давно вас не видели!\n\n"
                    f"Специально для вас \u2014 скидка 15% на следующий заказ.\n"
                    f"Используйте промокод: <b>RETURN15</b>\n\n"
                    f"Нажмите /start чтобы оформить заказ."
                )
                try:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=text,
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.debug("Не удалось отправить retention клиенту %d: %s", telegram_id, e)
            if inactive_clients:
                logger.info("Retention: отправлено %d напоминаний", len(inactive_clients))
        except Exception as e:
            logger.error("Ошибка retention_check: %s", e)

        await asyncio.sleep(86400)  # 24 часа


async def upsell_check(bot: Bot) -> None:
    """
    Задача апселла: каждые 24ч находит клиентов с 3+ заказами
    без подписки и предлагает подписку.
    """
    while True:
        try:
            all_clients = await database.get_all_clients_with_orders()
            for client in all_clients:
                order_count = client.get("order_count", 0)
                if order_count < 3:
                    continue
                telegram_id = client["telegram_id"]
                # Проверяем есть ли подписка
                sub = await subscriptions.check_subscription(telegram_id)
                if sub:
                    continue
                name = client.get("first_name") or "друг"
                text = (
                    f"\U0001f31f {name}, вы уже оформили {order_count} заказов!\n\n"
                    f"Подписка <b>BASIC</b> ({config.SUBSCRIPTION_BASIC_PRICE} \u20bd/мес) "
                    f"даст вам {config.SUBSCRIPTION_BASIC_ORDERS} заказов по выгодной цене.\n\n"
                    f"Подписка <b>PRO</b> ({config.SUBSCRIPTION_PRO_PRICE} \u20bd/мес) "
                    f"\u2014 безлимитные заказы.\n\n"
                    f"Нажмите /start и выберите \"\U0001f4ab Подписки\"."
                )
                try:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=text,
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.debug("Не удалось отправить upsell клиенту %d: %s", telegram_id, e)
            logger.info("Upsell check завершён")
        except Exception as e:
            logger.error("Ошибка upsell_check: %s", e)

        await asyncio.sleep(86400)  # 24 часа


async def subscription_expiry_check() -> None:
    """
    Задача истечения подписок: каждый час помечает
    истёкшие подписки как expired.
    """
    while True:
        try:
            await subscriptions.expire_subscriptions()
        except Exception as e:
            logger.error("Ошибка subscription_expiry_check: %s", e)

        await asyncio.sleep(3600)  # 1 час


def start_scheduler(bot: Bot) -> None:
    """
    Запустить все фоновые задачи в текущем event loop.

    Вызывается из post_init хука Application.
    """
    loop = asyncio.get_event_loop()
    loop.create_task(retention_check(bot))
    loop.create_task(upsell_check(bot))
    loop.create_task(subscription_expiry_check())
    logger.info("Планировщик задач запущен (retention, upsell, subscription_expiry)")
