"""Планировщик фоновых задач AI-агентства: retention, upsell, подписки, лиды, автопостинг."""

import asyncio
import logging

from telegram import Bot

import config
import database
import subscriptions
import lead_parser
import auto_posting

# Интеграция backup, CRM и мониторинга (graceful)
try:
    import backup
except ImportError:
    backup = None

try:
    import crm
except ImportError:
    crm = None

try:
    import monitoring
except ImportError:
    monitoring = None

logger = logging.getLogger(__name__)


async def retention_check(bot: Bot) -> None:
    """
    Задача удержания: каждые 24ч проверяет клиентов,
    неактивных 7+ дней, и отправляет напоминание.
    Использует last_notified_at для дедупликации (cooldown 7 дней).
    """
    while True:
        try:
            inactive_clients = await database.get_clients_inactive_days_not_notified(
                days=7, cooldown_hours=168
            )
            sent = 0
            for client in inactive_clients:
                telegram_id = client["telegram_id"]
                name = client.get("first_name") or "друг"
                text = (
                    f"\U0001f44b {name}, давно вас не видели!\n\n"
                    f"Специально для вас \u2014 скидка на следующий заказ.\n\n"
                    f"Нажмите /start чтобы оформить заказ."
                )
                try:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=text,
                        parse_mode="HTML",
                    )
                    await database.update_client_last_notified(telegram_id)
                    sent += 1
                except Exception as e:
                    logger.debug("Не удалось отправить retention клиенту %d: %s", telegram_id, e)
            if sent:
                logger.info("Retention: отправлено %d напоминаний", sent)
        except Exception as e:
            logger.error("Ошибка retention_check: %s", e)

        await asyncio.sleep(86400)  # 24 часа


async def upsell_check(bot: Bot) -> None:
    """
    Задача апселла: каждые 24ч находит клиентов с 3+ заказами
    без подписки и предлагает подписку.
    Использует last_upsell_at для дедупликации (cooldown 7 дней).
    """
    while True:
        try:
            candidates = await database.get_clients_for_upsell_not_notified(
                min_orders=3, cooldown_hours=168
            )
            sent = 0
            for client in candidates:
                telegram_id = client["telegram_id"]
                order_count = client.get("order_count", 0)
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
                    await database.update_client_last_upsell(telegram_id)
                    sent += 1
                except Exception as e:
                    logger.debug("Не удалось отправить upsell клиенту %d: %s", telegram_id, e)
            if sent:
                logger.info("Upsell: отправлено %d предложений", sent)
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


async def lead_parser_check(bot: Bot) -> None:
    """
    Задача парсинга лидов: каждые 15 минут проверяет
    новые заказы на Kwork по ключевым словам.
    """
    while True:
        try:
            await lead_parser.check_new_leads(bot)
        except Exception as e:
            logger.error("Ошибка lead_parser_check: %s", e)

        await asyncio.sleep(900)  # 15 минут


async def auto_posting_check(bot: Bot) -> None:
    """
    Задача автопостинга: каждый час публикует кейсы
    завершённых заказов с высокой оценкой в канал.
    """
    while True:
        try:
            await auto_posting.check_and_post_cases(bot)
        except Exception as e:
            logger.error("Ошибка auto_posting_check: %s", e)

        await asyncio.sleep(3600)  # 1 час


async def backup_check() -> None:
    """
    Задача бэкапа: ежедневно создаёт резервную копию БД
    и удаляет старые бэкапы.
    """
    while True:
        try:
            if backup:
                await backup.backup_database()
                await backup.cleanup_old_backups()
                logger.info("Бэкап выполнен успешно")
        except Exception as e:
            logger.error("Ошибка backup_check: %s", e)

        await asyncio.sleep(86400)  # 24 часа


async def crm_segment_update() -> None:
    """
    Задача обновления сегментов CRM: каждые 6 часов
    пересчитывает сегменты всех клиентов.
    """
    while True:
        try:
            if crm:
                stats = await crm.update_segments()
                logger.info("CRM сегменты обновлены: %s", stats)
        except Exception as e:
            logger.error("Ошибка crm_segment_update: %s", e)

        await asyncio.sleep(21600)  # 6 часов


async def crm_send_offers(bot: Bot) -> None:
    """
    Задача отправки персональных предложений CRM: каждые 24 часа
    отправляет предложения клиентам на основе их сегмента.
    Использует last_notified_at для дедупликации.
    """
    while True:
        try:
            if crm:
                clients = await database.get_clients_inactive_days_not_notified(
                    days=3, cooldown_hours=168
                )
                sent = 0
                for client in clients:
                    telegram_id = client["telegram_id"]
                    segment = await crm.get_client_segment(telegram_id)
                    # Only send offers to sleeping/active/vip segments
                    if segment == "new":
                        continue
                    offer_text = crm.get_personal_offer(segment)
                    try:
                        await bot.send_message(
                            chat_id=telegram_id,
                            text=offer_text,
                            parse_mode="HTML",
                        )
                        await database.update_client_last_notified(telegram_id)
                        sent += 1
                    except Exception as e:
                        logger.debug(
                            "Не удалось отправить CRM-предложение клиенту %d: %s",
                            telegram_id, e,
                        )
                if sent:
                    logger.info("CRM offers: отправлено %d предложений", sent)
        except Exception as e:
            logger.error("Ошибка crm_send_offers: %s", e)

        await asyncio.sleep(86400)  # 24 часа


async def monitoring_watchdog() -> None:
    """
    Задача мониторинга: каждые 5 минут проверяет здоровье системы
    и отправляет алерт если какой-то компонент не работает.
    """
    while True:
        try:
            if monitoring:
                health = await monitoring.health_check()
                if health.get("status") != "healthy":
                    # Формируем сообщение об ошибках
                    failed_checks = []
                    for name, check in health.get("checks", {}).items():
                        if check.get("status") not in ("ok", "skipped"):
                            failed_checks.append(f"{name}: {check.get('detail', 'unknown')}")
                    if failed_checks:
                        alert_msg = "Проблемы с компонентами:\n" + "\n".join(failed_checks)
                        await monitoring.send_alert_to_admin(alert_msg)
        except Exception as e:
            logger.error("Ошибка monitoring_watchdog: %s", e)

        await asyncio.sleep(300)  # 5 минут


def start_scheduler(bot: Bot) -> None:
    """
    Запустить все фоновые задачи в текущем event loop.

    Вызывается из post_init хука Application.
    Задачи запускаются с разнесением по времени (stagger),
    чтобы избежать одновременного всплеска запросов к БД и сети.
    """
    loop = asyncio.get_event_loop()

    async def _staggered_start(coro, delay: float):
        """Запустить корутину после начальной задержки."""
        if delay > 0:
            await asyncio.sleep(delay)
        await coro

    loop.create_task(_staggered_start(retention_check(bot), 0))
    loop.create_task(_staggered_start(upsell_check(bot), 10))
    loop.create_task(_staggered_start(subscription_expiry_check(), 20))
    loop.create_task(_staggered_start(lead_parser_check(bot), 30))
    loop.create_task(_staggered_start(auto_posting_check(bot), 60))
    loop.create_task(_staggered_start(backup_check(), 90))
    loop.create_task(_staggered_start(crm_segment_update(), 120))
    loop.create_task(_staggered_start(crm_send_offers(bot), 150))
    loop.create_task(_staggered_start(monitoring_watchdog(), 180))
    logger.info(
        "Планировщик задач запущен (retention, upsell, subscription_expiry, "
        "lead_parser, auto_posting, backup, crm_segment_update, crm_send_offers, monitoring_watchdog)"
    )
