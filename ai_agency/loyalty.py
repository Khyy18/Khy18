"""Модуль программы лояльности AI-агентства."""

import logging
from typing import Optional, Tuple

import aiosqlite

import config
from utils import progress_bar_slim, format_number

logger = logging.getLogger(__name__)

# Уровни лояльности: (имя, min_spent, max_spent, discount, emoji)
LOYALTY_LEVELS = [
    ("bronze", 0, 999, 0.0, "\U0001f949"),
    ("silver", 1000, 4999, 0.05, "\U0001f948"),
    ("gold", 5000, 14999, 0.10, "\U0001f947"),
    ("platinum", 15000, float("inf"), 0.15, "\U0001f48e"),
]

# Привилегии по уровням
LOYALTY_PRIVILEGES = {
    "bronze": ["Базовые цены"],
    "silver": ["-5% на все услуги", "Приоритетная очередь"],
    "gold": ["-10% на все услуги", "Бесплатная срочность", "Персональный стиль"],
    "platinum": ["-15% на все услуги", "Эксклюзивные промпты", "Бесплатные документы"],
}


def _determine_level(total_spent: float) -> Tuple[str, dict]:
    """Определить уровень лояльности по сумме расходов."""
    for name, min_spent, max_spent, discount, emoji in LOYALTY_LEVELS:
        if min_spent <= total_spent <= max_spent:
            return name, {
                "name": name,
                "min_spent": min_spent,
                "max_spent": max_spent if max_spent != float("inf") else None,
                "discount": discount,
                "emoji": emoji,
            }
    # Default fallback
    return "bronze", {
        "name": "bronze",
        "min_spent": 0,
        "max_spent": 999,
        "discount": 0.0,
        "emoji": "\U0001f949",
    }


async def get_loyalty_level(telegram_id: int) -> dict:
    """
    Получить информацию об уровне лояльности клиента.

    Returns:
        dict с ключами: name, min_spent, max_spent, discount, emoji,
        total_spent, privileges, progress_bar, next_level_at
    """
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT total_spent FROM clients WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = await cursor.fetchone()
            total_spent = row[0] if row else 0.0
    except Exception as e:
        logger.debug("Ошибка получения total_spent для loyalty: %s", e)
        total_spent = 0.0

    level_name, level_info = _determine_level(total_spent)
    privileges = LOYALTY_PRIVILEGES.get(level_name, [])

    # Прогресс до следующего уровня
    next_level_at = None
    progress = ""
    for i, (name, min_s, max_s, _, _) in enumerate(LOYALTY_LEVELS):
        if name == level_name and i < len(LOYALTY_LEVELS) - 1:
            next_name, next_min, _, _, _ = LOYALTY_LEVELS[i + 1]
            next_level_at = next_min
            spent_in_level = total_spent - min_s
            level_range = next_min - min_s
            progress = progress_bar_slim(
                int(spent_in_level), int(level_range)
            )
            break

    result = {
        **level_info,
        "total_spent": total_spent,
        "privileges": privileges,
        "progress_bar": progress,
        "next_level_at": next_level_at,
    }
    return result


async def get_loyalty_discount(telegram_id: int) -> float:
    """
    Получить скидку лояльности для клиента.

    Returns:
        Значение скидки от 0.0 до 0.15 (например 0.10 = 10%)
    """
    if not getattr(config, "LOYALTY_ENABLED", True):
        return 0.0

    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT total_spent FROM clients WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = await cursor.fetchone()
            total_spent = row[0] if row else 0.0
    except Exception as e:
        logger.debug("Ошибка получения loyalty discount: %s", e)
        return 0.0

    level_name, level_info = _determine_level(total_spent)
    return level_info["discount"]


async def get_loyalty_info(telegram_id: int) -> str:
    """
    Получить карточку лояльности для отображения в боте.

    Returns:
        HTML-текстовая карточка с информацией о уровне, прогрессе и привилегиях
    """
    info = await get_loyalty_level(telegram_id)

    body_lines = [
        f"Уровень: {info['emoji']} <b>{info['name'].capitalize()}</b>",
        f"Потрачено: {format_number(info['total_spent'])} \u20bd",
    ]

    if info["progress_bar"] and info["next_level_at"] is not None:
        body_lines.append(
            f"До следующего: {info['progress_bar']} ({format_number(info['next_level_at'])} \u20bd)"
        )

    body_lines.append("")
    body_lines.append("<b>Привилегии:</b>")
    for priv in info["privileges"]:
        body_lines.append(f"  \u2022 {priv}")

    if info["discount"] > 0:
        body_lines.append("")
        body_lines.append(
            f"\U0001f4b0 Ваша скидка: <b>-{int(info['discount'] * 100)}%</b> на все услуги"
        )

    from utils import _card
    return _card("Программа лояльности", "\U0001f3c6", body_lines)


async def check_level_up(telegram_id: int, new_total_spent: float) -> Optional[str]:
    """
    Проверить, повысился ли уровень после нового расхода.

    Args:
        telegram_id: ID клиента
        new_total_spent: новая общая сумма расходов

    Returns:
        Текст уведомления о повышении уровня, или None
    """
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT loyalty_notified_level FROM clients WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = await cursor.fetchone()
            current_notified = row[0] if row and row[0] else "bronze"
    except Exception as e:
        logger.debug("Ошибка проверки level_up: %s", e)
        return None

    new_level_name, new_level_info = _determine_level(new_total_spent)

    # Проверяем, что новый уровень выше текущего уведомлённого
    level_order = ["bronze", "silver", "gold", "platinum"]
    current_idx = level_order.index(current_notified) if current_notified in level_order else 0
    new_idx = level_order.index(new_level_name) if new_level_name in level_order else 0

    if new_idx <= current_idx:
        return None

    # Обновляем уведомлённый уровень в БД
    try:
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute(
                "UPDATE clients SET loyalty_notified_level = ? WHERE telegram_id = ?",
                (new_level_name, telegram_id),
            )
            await db.commit()
    except Exception as e:
        logger.debug("Ошибка обновления loyalty_notified_level: %s", e)

    privileges = LOYALTY_PRIVILEGES.get(new_level_name, [])
    priv_text = "\n".join(f"  \u2022 {p}" for p in privileges)

    return (
        f"\U0001f389 <b>Поздравляем!</b>\n\n"
        f"Вы достигли уровня {new_level_info['emoji']} <b>{new_level_name.capitalize()}</b>!\n\n"
        f"Ваши новые привилегии:\n{priv_text}"
    )
