"""Точка входа бота мониторинга цен."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import settings
from bot.db.models import init_db
from bot.handlers.start import router as start_router
from bot.handlers.alerts import router as alerts_router
from bot.handlers.subscription import router as subscription_router
from bot.handlers.seller import router as seller_router
from bot.handlers.referral import router as referral_router

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
