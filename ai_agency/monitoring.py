"""Мониторинг, health-check и алертинг для AI-агентства."""

import asyncio
import logging
import time
from collections import deque
from typing import Dict, Optional

import aiosqlite
from telegram import Bot

import config

logger = logging.getLogger(__name__)

# Метрики хранятся как deque с ограничением по размеру
_error_log: deque = deque(maxlen=1000)
_request_log: deque = deque(maxlen=1000)
_start_time: float = time.time()


class MetricsCollector:
    """Сборщик метрик системы."""

    def __init__(self):
        self.orders_in_queue: int = 0
        self.total_orders_processed: int = 0
        self.total_errors: int = 0
        self._processing_times: deque = deque(maxlen=100)

    def record_order_processed(self, duration: float) -> None:
        """Записать обработку заказа."""
        self.total_orders_processed += 1
        self._processing_times.append(duration)
        _request_log.append(time.time())

    def record_error(self) -> None:
        """Записать ошибку."""
        self.total_errors += 1
        _error_log.append(time.time())

    @property
    def avg_processing_time(self) -> float:
        """Среднее время обработки заказа."""
        if not self._processing_times:
            return 0.0
        return sum(self._processing_times) / len(self._processing_times)

    @property
    def error_rate(self) -> float:
        """Процент ошибок за последний час."""
        hour_ago = time.time() - 3600
        recent_errors = sum(1 for t in _error_log if t > hour_ago)
        recent_requests = sum(1 for t in _request_log if t > hour_ago)
        if recent_requests == 0:
            return 0.0
        return recent_errors / recent_requests * 100

    @property
    def uptime(self) -> float:
        """Время работы в секундах."""
        return time.time() - _start_time

    def get_metrics(self) -> Dict:
        """Получить все метрики."""
        return {
            "orders_in_queue": self.orders_in_queue,
            "avg_processing_time": round(self.avg_processing_time, 2),
            "error_rate": round(self.error_rate, 2),
            "uptime_seconds": round(self.uptime, 0),
            "total_orders_processed": self.total_orders_processed,
            "total_errors": self.total_errors,
        }


# Глобальный экземпляр сборщика метрик
metrics = MetricsCollector()


async def health_check() -> Dict:
    """
    Проверка здоровья системы.

    Проверяет:
    - Доступность БД (SELECT 1)
    - Доступность OpenAI API
    - Отзывчивость бота (getMe)

    Возвращает dict с результатами проверок.
    """
    results = {
        "status": "healthy",
        "checks": {},
    }

    # Проверка БД
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute("SELECT 1")
        results["checks"]["database"] = {"status": "ok"}
    except Exception as e:
        results["checks"]["database"] = {"status": "error", "detail": str(e)}
        results["status"] = "unhealthy"

    # Проверка OpenAI API
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        await asyncio.wait_for(
            client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            ),
            timeout=10.0,
        )
        results["checks"]["openai"] = {"status": "ok"}
    except Exception as e:
        results["checks"]["openai"] = {"status": "error", "detail": str(e)}
        results["status"] = "degraded"

    # Проверка бота
    try:
        if config.TELEGRAM_BOT_TOKEN:
            bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
            await asyncio.wait_for(bot.get_me(), timeout=5.0)
            results["checks"]["telegram_bot"] = {"status": "ok"}
        else:
            results["checks"]["telegram_bot"] = {"status": "skipped", "detail": "no token"}
    except Exception as e:
        results["checks"]["telegram_bot"] = {"status": "error", "detail": str(e)}
        results["status"] = "degraded"

    results["metrics"] = metrics.get_metrics()
    return results


async def send_alert_to_admin(message: str) -> None:
    """Отправить алерт администратору через Telegram."""
    if not config.ADMIN_TELEGRAM_ID or not config.TELEGRAM_BOT_TOKEN:
        logger.warning("Невозможно отправить алерт: ADMIN_TELEGRAM_ID или токен не задан")
        return

    try:
        bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        alert_text = f"\u26a0\ufe0f <b>ALERT</b>\n\n{message}"
        await bot.send_message(
            chat_id=config.ADMIN_TELEGRAM_ID,
            text=alert_text,
            parse_mode="HTML",
        )
        logger.info("Алерт отправлен админу: %s", message[:50])
    except Exception as e:
        logger.error("Не удалось отправить алерт: %s", e)


async def watchdog(interval: int = 300) -> None:
    """
    Watchdog: проверяет отзывчивость бота каждые interval секунд.

    Если бот не отвечает 5 минут (один цикл), отправляет алерт админу.
    """
    consecutive_failures = 0
    while True:
        try:
            await asyncio.sleep(interval)
            if not config.TELEGRAM_BOT_TOKEN:
                continue

            bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
            await asyncio.wait_for(bot.get_me(), timeout=10.0)
            consecutive_failures = 0
        except asyncio.CancelledError:
            break
        except Exception as e:
            consecutive_failures += 1
            logger.warning("Watchdog: бот не отвечает (попытка %d): %s", consecutive_failures, e)
            if consecutive_failures >= 1:
                await send_alert_to_admin(
                    f"Бот не отвечает уже {consecutive_failures * interval} секунд!\nОшибка: {e}"
                )
