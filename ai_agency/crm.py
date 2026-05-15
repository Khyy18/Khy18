"""CRM: сегментация клиентов и персональные предложения."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

import aiosqlite

import config

logger = logging.getLogger(__name__)

# Пороги сегментации
VIP_THRESHOLD = 5000  # total_spent > 5000
NEW_CLIENT_DAYS = 7
ACTIVE_DAYS = 14
SLEEPING_DAYS = 14


async def get_client_segment(telegram_id: int) -> str:
    """
    Определить сегмент клиента.

    Сегменты:
    - 'vip': total_spent > 5000
    - 'new': зарегистрирован менее 7 дней назад, 0 заказов
    - 'active': заказывал в последние 14 дней
    - 'sleeping': не заказывал более 14 дней
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM clients WHERE telegram_id = ?", (telegram_id,)
        )
        client = await cursor.fetchone()
        if not client:
            return "new"

        client = dict(client)

        # VIP по сумме трат
        if client.get("total_spent", 0) > VIP_THRESHOLD:
            return "vip"

        # Проверяем давность регистрации
        registered_at = client.get("registered_at", "")
        if registered_at:
            reg_date = datetime.fromisoformat(registered_at)
            if (datetime.utcnow() - reg_date).days < NEW_CLIENT_DAYS:
                # Проверяем есть ли заказы
                cursor2 = await db.execute(
                    "SELECT COUNT(*) FROM orders WHERE client_id = ?",
                    (telegram_id,),
                )
                row = await cursor2.fetchone()
                if row and row[0] == 0:
                    return "new"

        # Проверяем последний заказ
        threshold = (datetime.utcnow() - timedelta(days=ACTIVE_DAYS)).isoformat()
        cursor3 = await db.execute(
            "SELECT COUNT(*) FROM orders WHERE client_id = ? AND created_at >= ?",
            (telegram_id, threshold),
        )
        row = await cursor3.fetchone()
        if row and row[0] > 0:
            return "active"

        return "sleeping"


def get_personal_offer(segment: str) -> str:
    """
    Получить персональное предложение на основе сегмента.

    Возвращает текст предложения.
    """
    offers = {
        "new": (
            "\U0001f381 Добро пожаловать! Первый заказ бесплатно.\n"
            "Попробуйте наши услуги без риска!"
        ),
        "active": (
            "\U0001f525 Спасибо за активность! Скидка 10% на следующий заказ.\n"
            "Промокод: ACTIVE10"
        ),
        "vip": (
            "\U0001f451 VIP-клиент! Для вас персональная скидка 20%.\n"
            "Приоритетная обработка всех заказов.\nПромокод: VIP20"
        ),
        "sleeping": (
            "\U0001f634 Давно вас не видели! Скидка 15% на возвращение.\n"
            "Промокод: COMEBACK15"
        ),
    }
    return offers.get(segment, offers["new"])


async def get_client_timeline(telegram_id: int) -> List[dict]:
    """
    Получить таймлайн событий клиента (заказы, платежи).

    Для админского просмотра.
    """
    events: List[dict] = []
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Заказы
        cursor = await db.execute(
            "SELECT id, service_type, status, created_at, price FROM orders "
            "WHERE client_id = ? ORDER BY created_at DESC LIMIT 50",
            (telegram_id,),
        )
        rows = await cursor.fetchall()
        for row in rows:
            row = dict(row)
            events.append({
                "type": "order",
                "id": row["id"],
                "service_type": row["service_type"],
                "status": row["status"],
                "timestamp": row["created_at"],
                "amount": row["price"],
            })

        # Платежи
        cursor2 = await db.execute(
            "SELECT id, amount, method, created_at FROM payments "
            "WHERE client_id = ? ORDER BY created_at DESC LIMIT 50",
            (telegram_id,),
        )
        rows2 = await cursor2.fetchall()
        for row in rows2:
            row = dict(row)
            events.append({
                "type": "payment",
                "id": row["id"],
                "method": row["method"],
                "timestamp": row["created_at"],
                "amount": row["amount"],
            })

    # Сортируем по времени
    events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return events


async def update_segments() -> dict:
    """
    Пакетное обновление сегментов всех клиентов.

    Для вызова из планировщика.
    Возвращает статистику по сегментам.
    """
    stats = {"new": 0, "active": 0, "vip": 0, "sleeping": 0}

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT telegram_id FROM clients")
        clients = await cursor.fetchall()

    for client in clients:
        telegram_id = client["telegram_id"]
        segment = await get_client_segment(telegram_id)
        stats[segment] = stats.get(segment, 0) + 1

    logger.info("Сегментация обновлена: %s", stats)
    return stats
