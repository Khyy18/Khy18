"""Автопостинг кейсов в Telegram-канал для заказов с высокой оценкой."""

import re
import logging
from typing import Optional

import aiosqlite
import config

try:
    import reviews as reviews_module
except ImportError:
    reviews_module = None

logger = logging.getLogger(__name__)


def _anonymize_text(text: str) -> str:
    """Анонимизация текста: маскирование имён, email, телефонов."""
    # Маскируем email
    text = re.sub(
        r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
        '[email]',
        text,
    )
    # Маскируем телефоны (различные форматы)
    text = re.sub(
        r'(\+?\d[\d\s\-\(\)]{7,}\d)',
        '[phone]',
        text,
    )
    # Маскируем имена (слова с заглавной буквы идущие подряд, 2+ слов)
    text = re.sub(
        r'\b([A-ZА-ЯЁ][a-zа-яё]+\s+[A-ZА-ЯЁ][a-zа-яё]+)\b',
        '[name]',
        text,
    )
    return text


async def create_case(order: dict) -> str:
    """
    Сформировать текст кейса для публикации.

    Включает: тип услуги, анонимизированное описание задачи,
    фрагмент результата, оценку.
    """
    service_type = order.get("service_type", "unknown")
    input_text = order.get("input_text", "")
    output_text = order.get("output_text", "")
    rating = order.get("rating", 5)

    # Анонимизируем и обрезаем
    anonymized_input = _anonymize_text(input_text[:100])
    anonymized_output = _anonymize_text(output_text[:300])

    stars = "\u2b50" * rating

    case_text = (
        f"\U0001f4bc <b>Кейс: {service_type}</b>\n\n"
        f"\U0001f4dd <b>Задача:</b>\n{anonymized_input}...\n\n"
        f"\u2705 <b>Результат (фрагмент):</b>\n{anonymized_output}...\n\n"
        f"\U0001f31f <b>Оценка клиента:</b> {stars} ({rating}/5)\n\n"
        f"#кейс #{service_type} #AIагентство"
    )
    return case_text


async def post_case_to_channel(bot, case_text: str) -> bool:
    """Опубликовать кейс в Telegram-канал."""
    channel_id = config.CHANNEL_ID
    if not channel_id:
        logger.warning("CHANNEL_ID не задан, автопостинг невозможен")
        return False

    try:
        await bot.send_message(
            chat_id=channel_id,
            text=case_text,
            parse_mode="HTML",
        )
        return True
    except Exception as e:
        logger.error("Ошибка публикации кейса в канал: %s", e)
        return False


async def check_and_post_cases(bot) -> None:
    """
    Найти завершённые заказы с оценкой >= 4, которые ещё не опубликованы,
    создать кейс и опубликовать в канал.
    """
    if not config.CHANNEL_ID:
        return

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM orders
               WHERE status = 'completed'
               AND rating >= 4
               AND case_posted = 0
               ORDER BY completed_at DESC
               LIMIT 5""",
        )
        orders = await cursor.fetchall()

    posted = 0
    for order in orders:
        order_dict = dict(order)
        case_text = await create_case(order_dict)
        success = await post_case_to_channel(bot, case_text)

        if success:
            async with aiosqlite.connect(config.DATABASE_PATH) as db:
                await db.execute(
                    "UPDATE orders SET case_posted = 1 WHERE id = ?",
                    (order_dict["id"],),
                )
                await db.commit()
            posted += 1

    if posted:
        logger.info("Auto-posting: опубликовано %d кейсов", posted)


async def post_best_reviews(bot) -> None:
    """Post best approved reviews to channel (every 3 days)."""
    if reviews_module:
        await reviews_module.post_best_reviews(bot)
