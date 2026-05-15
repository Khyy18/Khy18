"""Модуль динамического ценообразования на основе спроса."""

import logging
from datetime import datetime, timedelta
from typing import Tuple

import aiosqlite

import config

logger = logging.getLogger(__name__)

# Конфигурация порогов (из config.py)
_SURGE_THRESHOLD = None
_DISCOUNT_THRESHOLD = None


def _get_surge_threshold() -> int:
    """Получить порог surge pricing из конфига."""
    return getattr(config, "DEMAND_SURGE_THRESHOLD", 10)


def _get_discount_threshold() -> int:
    """Получить порог скидки из конфига."""
    return getattr(config, "DEMAND_DISCOUNT_THRESHOLD", 2)


def _is_off_peak() -> bool:
    """Проверить, является ли текущее время низким спросом (ночь 0-7, выходные)."""
    now = datetime.utcnow()
    # Ночные часы (0-7 UTC)
    if 0 <= now.hour <= 7:
        return True
    # Выходные (суббота=5, воскресенье=6)
    if now.weekday() >= 5:
        return True
    return False


async def _count_orders_last_hour(service_type: str) -> int:
    """Подсчитать заказы за последний час для данного сервиса."""
    since = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE service_type = ? AND created_at >= ?",
                (service_type, since),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logger.debug("Ошибка подсчёта заказов для demand pricing: %s", e)
        return 0


async def get_demand_multiplier(service_type: str) -> Tuple[float, str]:
    """
    Получить множитель цены на основе текущего спроса.

    Args:
        service_type: тип услуги (значение ServiceType)

    Returns:
        Кортеж (multiplier, label):
        - multiplier: коэффициент от 0.85 до 1.20
        - label: текст для отображения клиенту (пустая строка если нет изменения)
    """
    orders_count = await _count_orders_last_hour(service_type)
    surge_threshold = _get_surge_threshold()
    discount_threshold = _get_discount_threshold()

    # Surge pricing: высокий спрос
    if orders_count >= surge_threshold:
        # Линейная интерполяция: threshold -> +10%, threshold*2 -> +20%
        excess = min(orders_count - surge_threshold, surge_threshold)
        surge_percent = 10 + int(excess / max(surge_threshold, 1) * 10)
        surge_percent = min(surge_percent, 20)
        multiplier = 1.0 + surge_percent / 100
        return (multiplier, f"Surge +{surge_percent}%")

    # Night/weekend discount: низкий спрос
    if _is_off_peak() and orders_count <= discount_threshold:
        # Скидка 10-15% в зависимости от того, насколько мало заказов
        if orders_count == 0:
            discount_percent = 15
        else:
            discount_percent = 10
        multiplier = 1.0 - discount_percent / 100
        return (multiplier, f"Night discount -{discount_percent}%!")

    # Нормальная цена
    return (1.0, "")
