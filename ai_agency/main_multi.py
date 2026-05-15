"""Запуск нескольких Telegram-ботов и REST API конкурентно."""

import asyncio
import json
import logging
import signal
import sys

# Настройка логирования в первую очередь
try:
    from logging_config import setup_logging
    setup_logging()
except ImportError:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

import config
import database
from bot import create_application as create_main_application
from bot_factory import create_bot_application

# Интеграция модулей отказоустойчивости и очереди (graceful)
try:
    from resilience import GracefulShutdown, recover_stale_orders
    _graceful_shutdown = GracefulShutdown()
except ImportError:
    GracefulShutdown = None
    _graceful_shutdown = None
    recover_stale_orders = None

try:
    from queue_manager import OrderQueue
    _order_queue = OrderQueue()
except ImportError:
    _order_queue = None

try:
    import monitoring
except ImportError:
    monitoring = None

logger = logging.getLogger(__name__)


def _parse_niche_bots() -> list:
    """Разобрать JSON-конфигурацию нишевых ботов из config.NICHE_BOTS."""
    try:
        bots = json.loads(config.NICHE_BOTS)
        if not isinstance(bots, list):
            logger.warning("NICHE_BOTS is not a list, ignoring")
            return []
        return bots
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Failed to parse NICHE_BOTS: %s", e)
        return []


async def run_multi() -> None:
    """Запустить основной бот + нишевые боты конкурентно."""
    # Инициализация БД
    await database.init_db()

    # Восстановление зависших заказов
    if recover_stale_orders:
        recovered = await recover_stale_orders()
        if recovered:
            logger.info("Восстановлено %d зависших заказов при старте", recovered)

    # Инициализация таблиц API
    from api.auth import init_api_tables
    await init_api_tables()

    # Запуск очереди заказов
    if _order_queue:
        await _order_queue.start()
        logger.info("Очередь заказов запущена")
        # Передаём очередь в bot-модуль для использования при обработке заказов
        try:
            from bot import set_order_queue
            set_order_queue(_order_queue)
        except (ImportError, AttributeError):
            pass

    # Запуск watchdog мониторинга
    monitoring_task = None
    if monitoring:
        monitoring_task = asyncio.create_task(monitoring.watchdog(interval=300))
        logger.info("Watchdog мониторинга запущен")

    # Основной бот
    main_app = create_main_application()

    # Нишевые боты
    niche_configs = _parse_niche_bots()
    niche_apps = []
    for bot_cfg in niche_configs:
        token = bot_cfg.get("token", "")
        name = bot_cfg.get("name", "NicheBot")
        services = bot_cfg.get("services", [])
        persona = bot_cfg.get("persona_name", config.BOT_PERSONA_NAME)

        if not token:
            logger.warning("Skipping niche bot '%s': no token", name)
            continue

        app = create_bot_application(
            token=token,
            name=name,
            service_types=services,
            persona_name=persona,
        )
        niche_apps.append(app)
        logger.info("Created niche bot: %s (services: %s)", name, services)

    # Собираем все задачи
    shutdown_event = asyncio.Event()

    # Используем GracefulShutdown если доступен
    if _graceful_shutdown:
        try:
            _graceful_shutdown.register_signals()
        except (NotImplementedError, RuntimeError):
            pass
        shutdown_event = _graceful_shutdown.shutdown_event
    else:
        def _signal_handler() -> None:
            logger.info("Received shutdown signal")
            shutdown_event.set()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _signal_handler)
            except NotImplementedError:
                pass

    # Запускаем все боты
    all_apps = [main_app] + niche_apps

    async def run_bot(app) -> None:
        """Запустить бот в polling-режиме до получения сигнала остановки."""
        await app.initialize()
        await app.start()
        await app.updater.start_polling()

        # Ожидаем сигнал остановки
        await shutdown_event.wait()

        # Graceful shutdown
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

    tasks = [asyncio.create_task(run_bot(app)) for app in all_apps]

    logger.info(
        "Running %d bot(s): main + %d niche",
        len(all_apps), len(niche_apps),
    )

    # Ожидаем завершения всех задач или остановки
    try:
        await asyncio.gather(*tasks)
    except Exception as e:
        logger.error("Error in multi-bot runner: %s", e)
        shutdown_event.set()
        # Дожидаемся корректного завершения
        for task in tasks:
            if not task.done():
                task.cancel()
    finally:
        # Останавливаем очередь и мониторинг
        if _order_queue:
            await _order_queue.stop()
            logger.info("Очередь заказов остановлена")
        if monitoring_task and not monitoring_task.done():
            monitoring_task.cancel()
        if _graceful_shutdown:
            await _graceful_shutdown.wait_for_completion(timeout=30.0)


def main() -> None:
    """Точка входа для запуска мульти-бот архитектуры."""
    # Логирование уже настроено при импорте модуля (setup_logging выше)

    errors = config.validate_config()
    if errors:
        for err in errors:
            logger.error(err)
        sys.exit(1)

    asyncio.run(run_multi())


if __name__ == "__main__":
    main()
