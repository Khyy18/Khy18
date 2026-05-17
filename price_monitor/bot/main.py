"""Точка входа бота мониторинга цен."""

import asyncio
import logging
import signal
import time
from pathlib import Path
from typing import Any

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
from bot.handlers.admin_api import router as admin_api_router
from bot.logging_config import setup_logging
from bot.scheduler.tasks import cleanup_old_data_job, parse_prices_job, publish_digests_job

setup_logging()
logger = logging.getLogger(__name__)

# Heartbeat file path for health monitoring
HEARTBEAT_FILE = Path("/tmp/bot_heartbeat")

# Shutdown event for graceful termination
_shutdown_event = asyncio.Event()


def _signal_handler(sig: int, *args: Any) -> None:
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    logger.info("Received signal %s, initiating graceful shutdown...", signal.Signals(sig).name)
    _shutdown_event.set()


async def _heartbeat_job() -> None:
    """Write heartbeat timestamp for health monitoring."""
    HEARTBEAT_FILE.write_text(str(time.time()))


async def main() -> None:
    """Инициализация и запуск бота."""
    # Register signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler, sig)

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
    dp.include_router(admin_api_router)

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

    # Heartbeat for health monitoring
    scheduler.add_job(
        _heartbeat_job,
        trigger=IntervalTrigger(seconds=60),
        id="heartbeat",
        name="Bot heartbeat",
    )

    scheduler.start()

    logger.info("Бот запущен, начинаю polling...")
    try:
        # Start polling in a task so we can also await shutdown_event
        polling_task = asyncio.create_task(dp.start_polling(bot))
        shutdown_task = asyncio.create_task(_shutdown_event.wait())

        done, pending = await asyncio.wait(
            [polling_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    finally:
        logger.info("Shutting down gracefully...")
        scheduler.shutdown(wait=False)
        await close_db()
        await bot.session.close()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
