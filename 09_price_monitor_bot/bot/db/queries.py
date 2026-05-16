"""CRUD-функции для работы с базой данных."""

import json
import uuid
from typing import Any

import aiosqlite

from bot.config import settings


async def _get_db() -> aiosqlite.Connection:
    """Получить подключение к БД."""
    db = await aiosqlite.connect(settings.db_path)
    db.row_factory = aiosqlite.Row
    return db


# --- Products ---


async def add_product(
    marketplace: str,
    external_id: str,
    name: str,
    url: str,
    category: str | None = None,
    brand: str | None = None,
) -> int:
    """Добавить товар, вернуть id."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO products (marketplace, external_id, name, category, brand, url) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (marketplace, external_id, name, category, brand, url),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]
    finally:
        await db.close()


async def get_product_by_external_id(marketplace: str, external_id: str) -> dict[str, Any] | None:
    """Найти товар по marketplace + external_id."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM products WHERE marketplace = ? AND external_id = ?",
            (marketplace, external_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await db.close()


# --- Price History ---


async def add_price_record(
    product_id: int,
    price: float,
    old_price: float | None = None,
    discount_percent: float | None = None,
    is_fraud: bool = False,
) -> int:
    """Добавить запись о цене."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO price_history (product_id, price, old_price, discount_percent, is_fraud) "
            "VALUES (?, ?, ?, ?, ?)",
            (product_id, price, old_price, discount_percent, int(is_fraud)),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]
    finally:
        await db.close()


async def get_price_history(product_id: int, limit: int = 30) -> list[dict[str, Any]]:
    """Получить историю цен товара."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM price_history WHERE product_id = ? ORDER BY timestamp DESC LIMIT ?",
            (product_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


# --- Users ---


async def add_user(
    telegram_id: int,
    username: str | None = None,
    referral_code: str | None = None,
    referred_by: str | None = None,
) -> int:
    """Добавить пользователя."""
    if referral_code is None:
        referral_code = generate_referral_code()
    db = await _get_db()
    try:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, referral_code, referred_by) "
            "VALUES (?, ?, ?, ?)",
            (telegram_id, username, referral_code, referred_by),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]
    finally:
        await db.close()


async def get_user(telegram_id: int) -> dict[str, Any] | None:
    """Получить пользователя по telegram_id."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        result = dict(row)
        result["interests"] = json.loads(result.get("interests") or "[]")
        return result
    finally:
        await db.close()


async def update_user_vip(telegram_id: int, is_vip: bool) -> None:
    """Обновить VIP-статус пользователя."""
    db = await _get_db()
    try:
        await db.execute(
            "UPDATE users SET is_vip = ? WHERE telegram_id = ?",
            (int(is_vip), telegram_id),
        )
        await db.commit()
    finally:
        await db.close()


async def get_user_by_referral_code(code: str) -> dict[str, Any] | None:
    """Найти пользователя по реферальному коду."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE referral_code = ?", (code,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        await db.close()


def generate_referral_code() -> str:
    """Генерация уникального реферального кода."""
    return uuid.uuid4().hex[:8]


async def get_referral_count(referral_code: str) -> int:
    """Количество пользователей, пришедших по реферальной ссылке."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM users WHERE referred_by = ?",
            (referral_code,),
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0  # type: ignore[index]
    finally:
        await db.close()


# --- Alerts ---


async def add_alert(user_id: int, keyword: str, max_price: float | None = None) -> int:
    """Добавить алерт."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO alerts (user_id, keyword, max_price) VALUES (?, ?, ?)",
            (user_id, keyword, max_price),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]
    finally:
        await db.close()


async def get_user_alerts(user_id: int) -> list[dict[str, Any]]:
    """Получить алерты пользователя."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM alerts WHERE user_id = ? AND is_active = 1", (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def delete_alert(alert_id: int) -> None:
    """Деактивировать алерт."""
    db = await _get_db()
    try:
        await db.execute(
            "UPDATE alerts SET is_active = 0 WHERE id = ?", (alert_id,)
        )
        await db.commit()
    finally:
        await db.close()


async def get_active_alerts_for_keyword(keyword: str) -> list[dict[str, Any]]:
    """Получить все активные алерты по ключевому слову."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM alerts WHERE keyword LIKE ? AND is_active = 1",
            (f"%{keyword}%",),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


# --- Seller Monitors ---


async def add_seller_monitor(
    user_id: int, competitor_url: str, marketplace: str
) -> int:
    """Добавить мониторинг конкурента."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO seller_monitors (user_id, competitor_url, marketplace) VALUES (?, ?, ?)",
            (user_id, competitor_url, marketplace),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]
    finally:
        await db.close()


async def get_user_monitors(user_id: int) -> list[dict[str, Any]]:
    """Получить мониторы конкурентов для пользователя."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM seller_monitors WHERE user_id = ?", (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def delete_seller_monitor(monitor_id: int) -> None:
    """Удалить мониторинг конкурента."""
    db = await _get_db()
    try:
        await db.execute(
            "DELETE FROM seller_monitors WHERE id = ?", (monitor_id,)
        )
        await db.commit()
    finally:
        await db.close()


async def get_top_referrers(limit: int = 5) -> list[dict[str, Any]]:
    """Получить топ рефереров по количеству приглашений."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "SELECT u.telegram_id, u.username, COUNT(r.id) as count "
            "FROM users u JOIN users r ON r.referred_by = u.referral_code "
            "GROUP BY u.id ORDER BY count DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


# --- Posts ---


async def add_post(product_id: int, channel_id: int, text: str) -> int:
    """Добавить запись о публикации."""
    db = await _get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO posts (product_id, channel_id, text) VALUES (?, ?, ?)",
            (product_id, channel_id, text),
        )
        await db.commit()
        return cursor.lastrowid  # type: ignore[return-value]
    finally:
        await db.close()
