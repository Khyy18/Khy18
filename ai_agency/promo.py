"""Промокоды и партнёрская программа AI-агентства."""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import aiosqlite

import config
import database

logger = logging.getLogger(__name__)


# --- Промокоды ---

async def create_promo(
    code: str,
    discount_type: str = "percentage",
    discount_value: float = 10.0,
    max_uses: int = 0,
    expires_at: Optional[str] = None,
) -> Optional[int]:
    """
    Создать промокод.

    discount_type: 'percentage' или 'fixed'
    max_uses: 0 = неограничено
    expires_at: ISO datetime строка или None
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        try:
            cursor = await db.execute(
                """INSERT INTO promo_codes (code, discount_type, discount_value, max_uses, expires_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (code.upper(), discount_type, discount_value, max_uses, expires_at),
            )
            await db.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.warning("Ошибка создания промокода %s: %s", code, e)
            return None


async def validate_promo(code: str) -> Optional[Dict]:
    """
    Проверить промокод: активен, не истёк, лимит не исчерпан.

    Возвращает данные промокода или None если невалиден.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM promo_codes WHERE code = ? AND active = 1",
            (code.upper(),),
        )
        row = await cursor.fetchone()
        if not row:
            return None

        promo = dict(row)

        # Проверяем срок действия
        if promo.get("expires_at"):
            try:
                expires = datetime.fromisoformat(promo["expires_at"])
                if datetime.utcnow() > expires:
                    return None
            except (ValueError, TypeError):
                pass

        # Проверяем лимит использований
        if promo["max_uses"] > 0 and promo["used_count"] >= promo["max_uses"]:
            return None

        return promo


async def apply_promo(code: str, original_price: float) -> Tuple[float, Optional[Dict]]:
    """
    Применить промокод к цене.

    Возвращает (новая_цена, данные_промокода) или (original_price, None) если невалиден.
    """
    promo = await validate_promo(code)
    if not promo:
        return original_price, None

    if promo["discount_type"] == "percentage":
        discount = original_price * promo["discount_value"] / 100
    else:  # fixed
        discount = promo["discount_value"]

    new_price = max(0, original_price - discount)

    # Инкрементируем used_count
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE promo_codes SET used_count = used_count + 1 WHERE code = ?",
            (code.upper(),),
        )
        await db.commit()

    return new_price, promo


async def list_promos(active_only: bool = True) -> List[Dict]:
    """Получить список промокодов."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if active_only:
            cursor = await db.execute(
                "SELECT * FROM promo_codes WHERE active = 1 ORDER BY created_at DESC"
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM promo_codes ORDER BY created_at DESC"
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def delete_promo(code: str) -> bool:
    """Деактивировать промокод (soft delete)."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "UPDATE promo_codes SET active = 0 WHERE code = ?",
            (code.upper(),),
        )
        await db.commit()
        return cursor.rowcount > 0


# --- Партнёрская программа ---

async def generate_partner_link(partner_id: int) -> str:
    """Сгенерировать партнёрскую ссылку."""
    bot_username = config.BOT_USERNAME
    return f"https://t.me/{bot_username}?start=partner_{partner_id}"


async def record_partner_earning(
    partner_id: int,
    referred_client_id: int,
    order_id: int,
    order_amount: float,
) -> float:
    """
    Записать доход партнёра от заказа привлечённого клиента.

    Начисляется комиссия с КАЖДОГО заказа приведённого клиента (не только первого).
    Возвращает сумму комиссии.
    """
    commission = order_amount * config.PARTNER_COMMISSION_PERCENT / 100

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO partner_earnings (partner_id, referred_client_id, order_id, amount)
               VALUES (?, ?, ?, ?)""",
            (partner_id, referred_client_id, order_id, commission),
        )
        await db.commit()

    return commission


async def get_partner_stats(partner_id: int) -> Dict:
    """Получить статистику партнёра."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        # Общий доход
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM partner_earnings WHERE partner_id = ?",
            (partner_id,),
        )
        row = await cursor.fetchone()
        total_earnings = row[0] if row else 0.0
        total_orders = row[1] if row else 0

        # Количество привлечённых клиентов
        cursor2 = await db.execute(
            "SELECT COUNT(DISTINCT referred_client_id) FROM partner_earnings WHERE partner_id = ?",
            (partner_id,),
        )
        row2 = await cursor2.fetchone()
        referred_clients = row2[0] if row2 else 0

    return {
        "partner_id": partner_id,
        "total_earnings": total_earnings,
        "total_orders": total_orders,
        "referred_clients": referred_clients,
        "commission_percent": config.PARTNER_COMMISSION_PERCENT,
    }


async def withdraw_partner_earnings(partner_id: int) -> float:
    """
    Вывести партнёрские начисления на баланс.

    Возвращает сумму, зачисленную на баланс.
    """
    stats = await get_partner_stats(partner_id)
    total = stats["total_earnings"]

    if total <= 0:
        return 0.0

    # Зачисляем на баланс
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE clients SET balance = balance + ? WHERE telegram_id = ?",
            (total, partner_id),
        )
        # Очищаем записи партнёрских начислений (помечаем выведенными)
        # Для простоты удаляем записи
        await db.execute(
            "DELETE FROM partner_earnings WHERE partner_id = ?",
            (partner_id,),
        )
        await db.commit()

    return total
