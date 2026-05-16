"""Точка входа бота мониторинга цен."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from bot.config import settings
from bot.db.models import init_db
from bot.db.queries import close_db
from bot.handlers.start import router as start_router
from bot.handlers.alerts import router as alerts_router
from bot.handlers.subscription import router as subscription_router
from bot.handlers.seller import router as seller_router
from bot.handlers.referral import router as referral_router
from bot.scheduler.tasks import cleanup_old_data_job, parse_prices_job, publish_digests_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    """Инициализация и запуск бота."""
    logger.info("Инициализация базы данных...")
    await init_db()

    bot = Bot(token=settings.telegram_token, parse_mode="HTML")
    dp = Dispatcher()

    # Регистрация роутеров
    dp.include_router(start_router)
    dp.include_router(alerts_router)
    dp.include_router(subscription_router)
    dp.include_router(seller_router)
    dp.include_router(referral_router)

    # Планировщик задач
    scheduler = AsyncIOScheduler()

    # Парсинг цен каждые N минут (передаем bot для публикации)
    scheduler.add_job(
        parse_prices_job,
        trigger=IntervalTrigger(minutes=settings.parse_interval_minutes),
        args=[bot],
        id="parse_prices",
        name="Парсинг цен",
    )

    # Публикация дайджестов ежедневно в 10:00
    scheduler.add_job(
        publish_digests_job,
        trigger=CronTrigger(hour=10, minute=0),
        args=[bot],
        id="publish_digests",
        name="Публикация дайджестов",
    )

    # Очистка старых данных - по воскресеньям
    scheduler.add_job(
        cleanup_old_data_job,
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="cleanup_old_data",
        name="Очистка старых данных",
    )

    scheduler.start()

    logger.info("Бот запущен, начинаю polling...")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await close_db()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
