"""Планировщик фоновых задач AI-агентства: retention, upsell, подписки, лиды, автопостинг."""

import asyncio
import logging
from datetime import datetime

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

try:
    import sales_funnel
except ImportError:
    sales_funnel = None

try:
    import reviews as reviews_module
except ImportError:
    reviews_module = None

try:
    import service_discovery
except ImportError:
    service_discovery = None

try:
    import ad_manager
except ImportError:
    ad_manager = None

# Интеграция content_farm (graceful)
try:
    import content_farm
except ImportError:
    content_farm = None

# Интеграция marketplace (graceful)
try:
    import marketplace as marketplace_module
except ImportError:
    marketplace_module = None

# Интеграция demo_generator (graceful)
try:
    import demo_generator
except ImportError:
    demo_generator = None

# Интеграция retargeting (graceful)
try:
    import retargeting
except ImportError:
    retargeting = None

# Интеграция daily_report (graceful)
try:
    import daily_report
except ImportError:
    daily_report = None

# Интеграция fl_parser (graceful)
try:
    import fl_parser
except ImportError:
    fl_parser = None

# Интеграция tg_chat_parser (graceful)
try:
    import tg_chat_parser
except ImportError:
    tg_chat_parser = None

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


async def funnel_check(bot: Bot) -> None:
    """
    Задача воронки продаж: каждые 5 минут проверяет триггеры
    воронки для всех клиентов.
    """
    while True:
        try:
            if sales_funnel and config.FUNNEL_ENABLED:
                clients = await database.get_all_clients()
                triggered = 0
                for client in clients:
                    try:
                        if await sales_funnel.welcome_trigger(bot, client):
                            triggered += 1
                        elif await sales_funnel.trial_used_trigger(bot, client):
                            triggered += 1
                        elif await sales_funnel.subscription_push_trigger(bot, client):
                            triggered += 1
                        elif await sales_funnel.vip_reactivation_trigger(bot, client):
                            triggered += 1
                    except Exception as e:
                        logger.debug("Ошибка триггера для клиента %d: %s", client["telegram_id"], e)
                if triggered:
                    logger.info("Funnel: отправлено %d триггеров", triggered)
        except Exception as e:
            logger.error("Ошибка funnel_check: %s", e)

        await asyncio.sleep(300)  # 5 минут


async def review_posting_check(bot: Bot) -> None:
    """
    Задача публикации отзывов: каждые 3 дня публикует лучшие
    одобренные отзывы в канал.
    """
    while True:
        try:
            if reviews_module:
                await reviews_module.post_best_reviews(bot)
        except Exception as e:
            logger.error("Ошибка review_posting_check: %s", e)

        await asyncio.sleep(259200)  # 3 дня


async def service_discovery_check(bot: Bot) -> None:
    """
    Задача обнаружения трендов: ежедневно анализирует
    нераспознанные запросы и уведомляет админа о трендах.
    """
    while True:
        try:
            if service_discovery:
                await service_discovery.notify_admin_trends(bot)
        except Exception as e:
            logger.error("Ошибка service_discovery_check: %s", e)

        await asyncio.sleep(86400)  # 24 часа


async def ad_budget_check(bot: Bot) -> None:
    """
    Задача рекламного бюджета: еженедельно рассчитывает
    рекламный бюджет и уведомляет админа.
    """
    while True:
        try:
            if ad_manager:
                budget = await ad_manager.calculate_ad_budget(7)
                if budget > 0:
                    text = (
                        f"\U0001f4b0 <b>Рекламный бюджет на неделю</b>\n\n"
                        f"Бюджет: {budget:.0f} \u20bd "
                        f"({config.AD_BUDGET_PERCENT}% от выручки за 7 дней)"
                    )
                    try:
                        await bot.send_message(
                            chat_id=config.ADMIN_TELEGRAM_ID,
                            text=text,
                            parse_mode="HTML",
                        )
                    except Exception as e:
                        logger.debug("Не удалось отправить бюджет админу: %s", e)
        except Exception as e:
            logger.error("Ошибка ad_budget_check: %s", e)

        await asyncio.sleep(604800)  # 7 дней


async def content_farm_check(bot: Bot) -> None:
    """
    Задача контент-фермы: каждые 30 минут проверяет расписание
    и публикует посты в каналы.
    """
    while True:
        try:
            if content_farm:
                posted = await content_farm.check_and_post(bot)
                if posted:
                    logger.info("Content farm: опубликовано %d постов", posted)
        except Exception as e:
            logger.error("Ошибка content_farm_check: %s", e)

        await asyncio.sleep(1800)  # 30 минут


async def marketplace_replenish() -> None:
    """
    Задача пополнения маркетплейса: ежедневно генерирует
    новые шаблоны для каждой категории.
    """
    while True:
        try:
            if marketplace_module:
                for category in marketplace_module.CATEGORIES:
                    created = await marketplace_module.generate_new_templates(category, count=2)
                    if created:
                        logger.info(
                            "Marketplace: сгенерировано %d шаблонов для %s",
                            len(created), category,
                        )
        except Exception as e:
            logger.error("Ошибка marketplace_replenish: %s", e)

        await asyncio.sleep(86400)  # 24 часа


async def demo_generator_check(bot: Bot) -> None:
    """
    Задача генерации демо: ежедневно генерирует демо-контент
    и рекламные креативы для всех услуг.
    """
    while True:
        try:
            if demo_generator:
                demos = await demo_generator.auto_generate_demos()
                generated = sum(1 for v in demos.values() if v)
                if generated:
                    logger.info("Demo generator: сгенерировано %d демо", generated)
        except Exception as e:
            logger.error("Ошибка demo_generator_check: %s", e)

        await asyncio.sleep(86400)  # 24 часа


async def retargeting_check_task(bot: Bot) -> None:
    """
    Задача ретаргетинга: каждые 5 минут проверяет
    и отправляет ретаргетинг-сообщения.
    """
    while True:
        try:
            if retargeting:
                sent = await retargeting.process_retargeting(bot)
                if sent:
                    logger.info("Retargeting: отправлено %d сообщений", sent)
        except Exception as e:
            logger.error("Ошибка retargeting_check_task: %s", e)

        await asyncio.sleep(300)  # 5 минут


async def daily_report_check(bot: Bot) -> None:
    """
    Задача ежедневного отчёта: каждый день в DAILY_REPORT_HOUR
    отправляет владельцу сводку.
    """
    while True:
        try:
            if daily_report:
                now = datetime.utcnow()
                target_hour = config.DAILY_REPORT_HOUR
                # Check if current hour matches target
                if now.hour == target_hour and now.minute < 5:
                    await daily_report.send_daily_report(bot)
        except Exception as e:
            logger.error("Ошибка daily_report_check: %s", e)

        await asyncio.sleep(300)  # проверяем каждые 5 минут


async def ad_autopilot_check(bot: Bot) -> None:
    """
    Задача автопилота рекламы: каждый понедельник
    автоматически размещает рекламу если AD_AUTOPILOT=True.
    """
    while True:
        try:
            if ad_manager and config.AD_AUTOPILOT:
                now = datetime.utcnow()
                # Запускаем только по понедельникам (weekday=0) в 10:00
                if now.weekday() == 0 and now.hour == 10 and now.minute < 5:
                    await ad_manager.run_autopilot(bot)
        except Exception as e:
            logger.error("Ошибка ad_autopilot_check: %s", e)

        await asyncio.sleep(300)  # проверяем каждые 5 минут


async def fl_parser_check(bot: Bot) -> None:
    """
    Задача парсинга FL.ru: каждые 20 минут проверяет
    новые проекты по ключевым словам.
    """
    while True:
        try:
            if fl_parser:
                await fl_parser.check_new_fl_leads(bot)
        except Exception as e:
            logger.error("Ошибка fl_parser_check: %s", e)

        await asyncio.sleep(1200)  # 20 минут


async def tg_chat_parser_check(bot: Bot) -> None:
    """
    Задача мониторинга Telegram чатов: каждые 5 минут
    проверяет наличие заказов в отслеживаемых чатах.
    """
    while True:
        try:
            if tg_chat_parser and tg_chat_parser.is_configured():
                await tg_chat_parser.start_monitoring()
        except Exception as e:
            logger.error("Ошибка tg_chat_parser_check: %s", e)

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
    loop.create_task(_staggered_start(funnel_check(bot), 200))
    loop.create_task(_staggered_start(review_posting_check(bot), 220))
    loop.create_task(_staggered_start(service_discovery_check(bot), 240))
    loop.create_task(_staggered_start(ad_budget_check(bot), 260))
    loop.create_task(_staggered_start(content_farm_check(bot), 280))
    loop.create_task(_staggered_start(marketplace_replenish(), 300))
    loop.create_task(_staggered_start(demo_generator_check(bot), 320))
    loop.create_task(_staggered_start(retargeting_check_task(bot), 340))
    loop.create_task(_staggered_start(daily_report_check(bot), 360))
    loop.create_task(_staggered_start(ad_autopilot_check(bot), 380))
    loop.create_task(_staggered_start(fl_parser_check(bot), 400))
    loop.create_task(_staggered_start(tg_chat_parser_check(bot), 420))
    logger.info(
        "Планировщик задач запущен (retention, upsell, subscription_expiry, "
        "lead_parser, auto_posting, backup, crm_segment_update, crm_send_offers, "
        "monitoring_watchdog, funnel_check, review_posting, service_discovery, "
        "ad_budget, content_farm, marketplace_replenish, demo_generator, retargeting, "
        "daily_report, ad_autopilot, fl_parser, tg_chat_parser)"
    )
