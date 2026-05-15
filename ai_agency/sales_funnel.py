"""Воронка продаж AI-агентства: стадии, триггеры, конверсия."""

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List

import aiosqlite

import config
import database

logger = logging.getLogger(__name__)


class FunnelStage(str, Enum):
    """Стадии воронки продаж."""
    AWARENESS = "awareness"
    INTEREST = "interest"
    DESIRE = "desire"
    ACTION = "action"


# Настраиваемые шаблоны сообщений для каждого триггера
FUNNEL_TEMPLATES: Dict[str, str] = {
    "welcome": (
        "\U0001f44b {name}, добро пожаловать!\n\n"
        "Попробуйте наш сервис бесплатно - первый заказ за 0 \u20bd.\n"
        "Нажмите /start чтобы начать."
    ),
    "trial_used": (
        "\U0001f31f {name}, вам понравился результат?\n\n"
        "Специально для вас - скидка 30% на следующий заказ!\n"
        "Используйте промокод <b>FIRST30</b> при оформлении."
    ),
    "subscription_push": (
        "\U0001f4b0 {name}, вы уже оформили {order_count} заказов!\n\n"
        "С подпиской вы сэкономите {savings} \u20bd в месяц.\n"
        "Нажмите /start и выберите \"\U0001f4ab Подписки\"."
    ),
    "vip_reactivation": (
        "\U0001f451 {name}, мы скучаем по вам!\n\n"
        "Персональное предложение: скидка 20% на любой заказ.\n"
        "Промокод <b>VIP20</b> ждёт вас. Нажмите /start."
    ),
}


async def record_funnel_event(
    client_id: int, stage: FunnelStage, converted: bool = False
) -> None:
    """Записать событие воронки продаж."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        converted_at = datetime.utcnow().isoformat() if converted else None
        await db.execute(
            """INSERT INTO funnel_events (client_id, stage, triggered_at, converted_at)
               VALUES (?, ?, ?, ?)""",
            (client_id, stage.value, datetime.utcnow().isoformat(), converted_at),
        )
        await db.commit()


async def mark_conversion(client_id: int, stage: FunnelStage) -> None:
    """Отметить конверсию для клиента на указанной стадии."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            """UPDATE funnel_events SET converted_at = ?
               WHERE client_id = ? AND stage = ? AND converted_at IS NULL
               ORDER BY triggered_at DESC LIMIT 1""",
            (datetime.utcnow().isoformat(), client_id, stage.value),
        )
        await db.commit()


async def get_funnel_stats() -> Dict[str, Dict[str, int]]:
    """Получить статистику воронки: триггеры и конверсии по стадиям."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        stats = {}
        for stage in FunnelStage:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM funnel_events WHERE stage = ?",
                (stage.value,),
            )
            row = await cursor.fetchone()
            total = row[0] if row else 0

            cursor2 = await db.execute(
                "SELECT COUNT(*) FROM funnel_events WHERE stage = ? AND converted_at IS NOT NULL",
                (stage.value,),
            )
            row2 = await cursor2.fetchone()
            converted = row2[0] if row2 else 0

            stats[stage.value] = {
                "total": total,
                "converted": converted,
                "rate": round(converted / total * 100, 1) if total > 0 else 0.0,
            }
        return stats


async def welcome_trigger(bot, client: dict) -> bool:
    """
    Триггер приветствия: новый пользователь получает приветственное сообщение
    с предложением бесплатного триала (через 1 минуту после регистрации).
    """
    if not config.FUNNEL_ENABLED:
        return False

    client_id = client["telegram_id"]
    name = client.get("first_name") or "друг"

    # Проверяем, не отправляли ли уже
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM funnel_events WHERE client_id = ? AND stage = ?",
            (client_id, FunnelStage.AWARENESS.value),
        )
        if await cursor.fetchone():
            return False

    # Проверяем, что клиент зарегистрирован минимум 1 минуту назад
    registered_at = client.get("registered_at", "")
    if registered_at:
        try:
            reg_time = datetime.fromisoformat(registered_at)
            if datetime.utcnow() - reg_time < timedelta(minutes=1):
                return False
        except (ValueError, TypeError):
            pass

    text = FUNNEL_TEMPLATES["welcome"].format(name=name)
    try:
        await bot.send_message(chat_id=client_id, text=text, parse_mode="HTML")
        await record_funnel_event(client_id, FunnelStage.AWARENESS)
        return True
    except Exception as e:
        logger.debug("Не удалось отправить welcome триггер клиенту %d: %s", client_id, e)
        return False


async def trial_used_trigger(bot, client: dict) -> bool:
    """
    Триггер после использования триала: предложение скидки 30%
    (через 2 часа после использования триала).
    """
    if not config.FUNNEL_ENABLED:
        return False

    client_id = client["telegram_id"]
    name = client.get("first_name") or "друг"

    # Проверяем использован ли триал
    if not client.get("free_trial_used"):
        return False

    # Проверяем, не отправляли ли уже
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM funnel_events WHERE client_id = ? AND stage = ?",
            (client_id, FunnelStage.INTEREST.value),
        )
        if await cursor.fetchone():
            return False

    # Проверяем что триал использован минимум 2 часа назад (через заказы)
    orders = await database.get_orders_by_client(client_id, limit=1)
    if orders:
        first_order_time = orders[-1].get("created_at", "")
        try:
            order_time = datetime.fromisoformat(first_order_time)
            if datetime.utcnow() - order_time < timedelta(hours=2):
                return False
        except (ValueError, TypeError):
            pass

    text = FUNNEL_TEMPLATES["trial_used"].format(name=name)
    try:
        await bot.send_message(chat_id=client_id, text=text, parse_mode="HTML")
        await record_funnel_event(client_id, FunnelStage.INTEREST)
        return True
    except Exception as e:
        logger.debug("Не удалось отправить trial_used триггер клиенту %d: %s", client_id, e)
        return False


async def subscription_push_trigger(bot, client: dict) -> bool:
    """
    Триггер подписки: клиент с 3+ заказами без подписки получает
    предложение подписки с расчётом экономии.
    """
    if not config.FUNNEL_ENABLED:
        return False

    client_id = client["telegram_id"]
    name = client.get("first_name") or "друг"

    # Проверяем количество заказов
    order_count = await database.get_client_order_count(client_id)
    if order_count < 3:
        return False

    # Проверяем, не отправляли ли уже
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM funnel_events WHERE client_id = ? AND stage = ?",
            (client_id, FunnelStage.DESIRE.value),
        )
        if await cursor.fetchone():
            return False

    # Рассчитываем экономию
    avg_check = await database.get_avg_check()
    monthly_spend = avg_check * order_count
    savings = max(0, monthly_spend - config.SUBSCRIPTION_BASIC_PRICE)

    text = FUNNEL_TEMPLATES["subscription_push"].format(
        name=name,
        order_count=order_count,
        savings=int(savings),
    )
    try:
        await bot.send_message(chat_id=client_id, text=text, parse_mode="HTML")
        await record_funnel_event(client_id, FunnelStage.DESIRE)
        return True
    except Exception as e:
        logger.debug("Не удалось отправить subscription_push триггер клиенту %d: %s", client_id, e)
        return False


async def vip_reactivation_trigger(bot, client: dict) -> bool:
    """
    Триггер реактивации VIP: клиент с total_spent > 5000 без заказов 7 дней
    получает персональное предложение.
    """
    if not config.FUNNEL_ENABLED:
        return False

    client_id = client["telegram_id"]
    name = client.get("first_name") or "друг"

    # Проверяем VIP статус (потратил > 5000)
    total_spent = client.get("total_spent", 0)
    if total_spent < 5000:
        return False

    # Проверяем неактивность 7 дней
    orders = await database.get_orders_by_client(client_id, limit=1)
    if orders:
        last_order_time = orders[0].get("created_at", "")
        try:
            order_time = datetime.fromisoformat(last_order_time)
            if datetime.utcnow() - order_time < timedelta(days=7):
                return False
        except (ValueError, TypeError):
            pass
    else:
        # Нет заказов - не VIP
        return False

    # Проверяем, не отправляли ли уже (разрешаем повторные через 30 дней)
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """SELECT triggered_at FROM funnel_events
               WHERE client_id = ? AND stage = ?
               ORDER BY triggered_at DESC LIMIT 1""",
            (client_id, FunnelStage.ACTION.value),
        )
        row = await cursor.fetchone()
        if row:
            try:
                last_trigger = datetime.fromisoformat(row[0])
                if datetime.utcnow() - last_trigger < timedelta(days=30):
                    return False
            except (ValueError, TypeError):
                pass

    text = FUNNEL_TEMPLATES["vip_reactivation"].format(name=name)
    try:
        await bot.send_message(chat_id=client_id, text=text, parse_mode="HTML")
        await record_funnel_event(client_id, FunnelStage.ACTION)
        return True
    except Exception as e:
        logger.debug("Не удалось отправить vip_reactivation триггер клиенту %d: %s", client_id, e)
        return False
