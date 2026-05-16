"""Точка входа приложения AI Office.

Запуск Pyrogram client + FastAPI (uvicorn) + Proactive Scheduler параллельно через asyncio.
Graceful shutdown при получении SIGINT/SIGTERM.
"""

import asyncio
import signal

import uvicorn

from ai_office.api.main import app
from ai_office.core.config import settings
from ai_office.core.database import engine
from ai_office.core.proactive_tasks import (
    alice_daily_standup,
    eva_weekly_report,
    leo_overdue_alert,
    nova_health_check,
)
from ai_office.core.scheduler import scheduler
from ai_office.telegram.client import TelegramClient

shutdown_event = asyncio.Event()


async def run_api():
    """Запуск FastAPI через uvicorn с поддержкой graceful shutdown."""
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    server.should_exit = False
    task = asyncio.create_task(server.serve())
    await shutdown_event.wait()
    server.should_exit = True
    await task


async def run_telegram():
    """Запуск Telegram клиента с поддержкой graceful shutdown."""
    client = TelegramClient()
    await client.start()
    await shutdown_event.wait()
    await client.stop()


async def run_scheduler():
    """Запуск проактивного планировщика с graceful shutdown."""
    # Register proactive tasks
    scheduler.register_task(
        name="alice_standup",
        coro_factory=alice_daily_standup,
        hour=settings.standup_hour,
        minute=0,
    )
    scheduler.register_task(
        name="eva_weekly_report",
        coro_factory=eva_weekly_report,
        hour=10,
        minute=0,
        day_of_week=settings.weekly_report_day,
    )
    scheduler.register_task(
        name="leo_overdue_alert",
        coro_factory=leo_overdue_alert,
        interval_hours=settings.overdue_check_interval_hours,
    )
    scheduler.register_task(
        name="nova_health_check",
        coro_factory=nova_health_check,
        interval_hours=settings.health_check_interval_hours,
    )

    await scheduler.start(shutdown_event=shutdown_event)
    await shutdown_event.wait()
    await scheduler.stop()


async def main():
    """Главная функция - параллельный запуск всех сервисов с graceful shutdown."""
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: shutdown_event.set())

    await asyncio.gather(
        run_api(),
        run_telegram(),
        run_scheduler(),
        return_exceptions=True,
    )

    # Освобождение ресурсов
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
