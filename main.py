"""Точка входа AI Text Agency.

Запускает все сервисы агентства параллельно:
  - Health-check HTTP-сервер
  - Freelance scheduler (сканирование площадок)
  - Monitoring/alerts
  - Backup scheduler (через ARQ cron)
  - Task queue worker (ARQ)
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import Any

import logging_config
import sentry_setup


async def run_health_server() -> None:
    """Запуск health-check HTTP-сервера."""
    from aiohttp import web

    import config
    from health.server import create_health_app

    app = create_health_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.HEALTH_PORT)
    await site.start()
    # Keep running until cancelled
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await runner.cleanup()


async def run_freelance_scheduler() -> None:
    """Запуск планировщика фриланс-откликов."""
    from freelance_automation.config import KEYWORDS, PLATFORMS
    from freelance_automation.scheduler import FreelanceScheduler

    scheduler = FreelanceScheduler(platforms=PLATFORMS, keywords=KEYWORDS)
    await scheduler.run_forever()


async def run_alert_monitor() -> None:
    """Запуск фонового мониторинга метрик и алертов."""
    import aiohttp

    from monitoring.alerts import AlertManager

    mgr = AlertManager()
    async with aiohttp.ClientSession() as session:
        await mgr.run_loop(session)


async def run_task_queue_worker() -> None:
    """Запуск ARQ worker для фоновых задач."""
    from arq import create_pool

    from task_queue.config import get_redis_settings
    from task_queue.worker import WorkerSettings

    redis_settings = get_redis_settings()
    pool = await create_pool(redis_settings)
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await pool.close()


async def main() -> None:
    """Основная точка входа: запуск всех сервисов через asyncio.gather."""
    from logging_config import get_logger

    log = get_logger("main")

    # Инициализация логирования и Sentry
    logging_config.setup_logging()
    sentry_setup.init_sentry()

    log.info("agency_starting", services=[
        "health", "freelance_scheduler", "alert_monitor", "task_queue"
    ])

    # Настройка graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        log.info("shutdown_signal_received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    # Запуск всех сервисов
    tasks = [
        asyncio.create_task(run_health_server(), name="health"),
        asyncio.create_task(run_freelance_scheduler(), name="freelance"),
        asyncio.create_task(run_alert_monitor(), name="alerts"),
        asyncio.create_task(run_task_queue_worker(), name="task_queue"),
    ]

    # Ждём сигнала завершения
    await shutdown_event.wait()
    log.info("shutting_down")

    # Отменяем все задачи
    for task in tasks:
        task.cancel()

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for task, result in zip(tasks, results):
        if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
            log.error("task_error", task=task.get_name(), error=str(result))

    log.info("agency_stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
