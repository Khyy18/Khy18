"""Точка входа бота мониторинга цен."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import settings
from bot.db.models import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    """Инициализация и запуск бота."""
    logger.info("Инициализация базы данных...")
    await init_db()

    bot = Bot(token=settings.telegram_token, parse_mode="HTML")
    dp = Dispatcher()

    # Регистрация роутеров (будут добавлены в следующих фичах)
    # from bot.handlers import start, alerts, subscription, seller, referral
    # dp.include_router(start.router)
    # dp.include_router(alerts.router)
    # dp.include_router(subscription.router)
    # dp.include_router(seller.router)
    # dp.include_router(referral.router)

    # Планировщик задач
    scheduler = AsyncIOScheduler()
    # scheduler.add_job(...)  # Задачи будут добавлены позже
    scheduler.start()

    logger.info("Бот запущен, начинаю polling...")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
