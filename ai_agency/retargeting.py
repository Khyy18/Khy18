"""Модуль ретаргетинга AI-агентства: автоматические напоминания по сценариям."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite

import config

logger = logging.getLogger(__name__)

# Сценарии ретаргетинга: (event_type, delay_minutes, message_template)
SCENARIOS = [
    (
        "start",
        60,  # 1 час после /start без заказа
        "\U0001f44b Привет! Вы заглянули к нам, но ещё не попробовали. "
        "Первый заказ - бесплатно! Нажмите /start",
    ),
    (
        "order_started",
        30,  # 30 минут после начала заказа без подтверждения
        "\U0001f4dd Вы начали заказ, но не завершили. "
        "Готовый результат будет через 2 минуты! Нажмите /start",
    ),
    (
        "marketplace_view",
        120,  # 2 часа после просмотра маркетплейса
        "\U0001f6cd Нашли что-то интересное в маркетплейсе? "
        "Шаблоны от 50 \u20bd - готовы к использованию. Нажмите /start",
    ),
    (
        "low_rating",
        1440,  # 24 часа после оценки 3/5
        "\U0001f64f Мы заметили, что последний заказ мог быть лучше. "
        "Попробуйте ещё раз - мы улучшили качество! Скидка -10% по промокоду SORRY",
    ),
]

# Кулдаун: максимум 1 ретаргетинг-сообщение в день
COOLDOWN_HOURS = 24


async def track_event(telegram_id: int, event_type: str) -> None:
    """
    Записать событие пользователя для ретаргетинга.

    Args:
        telegram_id: ID пользователя
        event_type: тип события (start, order_started, marketplace_view, low_rating)
    """
    if not getattr(config, "RETARGETING_ENABLED", True):
        return

    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute(
                """INSERT INTO user_events (telegram_id, event_type, timestamp, processed)
                   VALUES (?, ?, ?, 0)""",
                (telegram_id, event_type, datetime.utcnow().isoformat()),
            )
            await db.commit()
    except Exception as e:
        logger.debug("Ошибка записи retargeting event: %s", e)


async def _check_cooldown(telegram_id: int) -> bool:
    """Проверить, можно ли отправить ретаргетинг (кулдаун не истёк)."""
    since = (datetime.utcnow() - timedelta(hours=COOLDOWN_HOURS)).isoformat()
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                """SELECT COUNT(*) FROM user_events
                   WHERE telegram_id = ? AND event_type = 'retargeting_sent'
                   AND timestamp >= ?""",
                (telegram_id, since),
            )
            row = await cursor.fetchone()
            return (row[0] if row else 0) == 0
    except Exception as e:
        logger.debug("Ошибка проверки cooldown: %s", e)
        return False


async def _has_converted(telegram_id: int, event_type: str, since: str) -> bool:
    """Проверить, совершил ли пользователь целевое действие после события."""
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            if event_type in ("start", "order_started", "marketplace_view"):
                # Проверяем, есть ли заказ после события
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM orders WHERE client_id = ? AND created_at >= ?",
                    (telegram_id, since),
                )
                row = await cursor.fetchone()
                return (row[0] if row else 0) > 0
            # Для low_rating - проверяем новый заказ
            cursor = await db.execute(
                "SELECT COUNT(*) FROM orders WHERE client_id = ? AND created_at >= ?",
                (telegram_id, since),
            )
            row = await cursor.fetchone()
            return (row[0] if row else 0) > 0
    except Exception:
        return True  # При ошибке считаем конвертированным (не отправляем)


async def _mark_sent(telegram_id: int) -> None:
    """Отметить отправку ретаргетинг-сообщения."""
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute(
                """INSERT INTO user_events (telegram_id, event_type, timestamp, processed)
                   VALUES (?, 'retargeting_sent', ?, 1)""",
                (telegram_id, datetime.utcnow().isoformat()),
            )
            await db.commit()
    except Exception as e:
        logger.debug("Ошибка отметки retargeting_sent: %s", e)


async def _mark_processed(event_id: int) -> None:
    """Пометить событие как обработанное."""
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute(
                "UPDATE user_events SET processed = 1 WHERE id = ?",
                (event_id,),
            )
            await db.commit()
    except Exception as e:
        logger.debug("Ошибка пометки processed: %s", e)


async def process_retargeting(bot) -> int:
    """
    Обработать все необработанные события ретаргетинга.

    Returns:
        Количество отправленных сообщений
    """
    if not getattr(config, "RETARGETING_ENABLED", True):
        return 0

    sent_count = 0

    for event_type, delay_minutes, message_text in SCENARIOS:
        threshold = (
            datetime.utcnow() - timedelta(minutes=delay_minutes)
        ).isoformat()

        try:
            async with aiosqlite.connect(config.DATABASE_PATH) as db:
                cursor = await db.execute(
                    """SELECT id, telegram_id, timestamp FROM user_events
                       WHERE event_type = ? AND processed = 0
                       AND timestamp <= ?
                       LIMIT 50""",
                    (event_type, threshold),
                )
                events = await cursor.fetchall()
        except Exception as e:
            logger.debug("Ошибка чтения events для %s: %s", event_type, e)
            continue

        for event in events:
            event_id, telegram_id, timestamp = event[0], event[1], event[2]

            # Пометить как обработанное в любом случае
            await _mark_processed(event_id)

            # Проверить кулдаун
            if not await _check_cooldown(telegram_id):
                continue

            # Проверить, не сконвертировался ли пользователь
            if await _has_converted(telegram_id, event_type, timestamp):
                continue

            # Отправить сообщение
            try:
                await bot.send_message(
                    chat_id=telegram_id,
                    text=message_text,
                    parse_mode="HTML",
                )
                await _mark_sent(telegram_id)
                sent_count += 1
            except Exception as e:
                logger.debug(
                    "Не удалось отправить retargeting %d: %s", telegram_id, e
                )

    return sent_count


async def retargeting_check(bot) -> None:
    """
    Бесконечный цикл проверки ретаргетинга (для scheduler).

    Проверяет каждые 5 минут.
    """
    while True:
        try:
            sent = await process_retargeting(bot)
            if sent:
                logger.info("Retargeting: отправлено %d сообщений", sent)
        except Exception as e:
            logger.error("Ошибка retargeting_check: %s", e)

        await asyncio.sleep(300)  # 5 минут
