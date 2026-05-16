"""CRUD-функции для работы с базой данных."""

import json
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import aiosqlite

from bot.config import settings

# Синглтон-соединение для переиспользования
_connection: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Получить общее подключение к БД (синглтон).

    SQLite - однопоточная БД с single-writer, поэтому одно
    соединение переиспользуется для всех запросов.
    """
    global _connection
    if _connection is None:
        _connection = await aiosqlite.connect(settings.db_path)
        _connection.row_factory = aiosqlite.Row
    return _connection


async def close_db() -> None:
    """Закрыть общее подключение к БД."""
    global _connection
    if _connection is not None:
        await _connection.close()
        _connection = None


@asynccontextmanager
async def db_session() -> AsyncIterator[aiosqlite.Connection]:
    """Контекстный менеджер для доступа к БД."""
    db = await get_db()
    yield db


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
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO products (marketplace, external_id, name, category, brand, url) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (marketplace, external_id, name, category, brand, url),
    )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


async def get_product_by_external_id(marketplace: str, external_id: str) -> dict[str, Any] | None:
    """Найти товар по marketplace + external_id."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM products WHERE marketplace = ? AND external_id = ?",
        (marketplace, external_id),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)


# --- Price History ---


async def add_price_record(
    product_id: int,
    price: float,
    old_price: float | None = None,
    discount_percent: float | None = None,
    is_fraud: bool = False,
) -> int:
    """Добавить запись о цене."""
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO price_history (product_id, price, old_price, discount_percent, is_fraud) "
        "VALUES (?, ?, ?, ?, ?)",
        (product_id, price, old_price, discount_percent, int(is_fraud)),
    )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


async def get_price_history(product_id: int, limit: int = 30) -> list[dict[str, Any]]:
    """Получить историю цен товара."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM price_history WHERE product_id = ? ORDER BY timestamp DESC LIMIT ?",
        (product_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


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
    db = await get_db()
    cursor = await db.execute(
        "INSERT OR IGNORE INTO users (telegram_id, username, referral_code, referred_by) "
        "VALUES (?, ?, ?, ?)",
        (telegram_id, username, referral_code, referred_by),
    )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


async def get_user(telegram_id: int) -> dict[str, Any] | None:
    """Получить пользователя по telegram_id."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    result = dict(row)
    result["interests"] = json.loads(result.get("interests") or "[]")
    return result


async def update_user_vip(telegram_id: int, is_vip: bool, days: int = 30) -> None:
    """Обновить VIP-статус пользователя с установкой даты истечения."""
    from datetime import datetime, timedelta

    db = await get_db()
    if is_vip:
        expires_at = (datetime.now() + timedelta(days=days)).isoformat()
        await db.execute(
            "UPDATE users SET is_vip = 1, vip_expires_at = ? WHERE telegram_id = ?",
            (expires_at, telegram_id),
        )
    else:
        await db.execute(
            "UPDATE users SET is_vip = 0, vip_expires_at = NULL WHERE telegram_id = ?",
            (telegram_id,),
        )
    await db.commit()


async def get_user_by_referral_code(code: str) -> dict[str, Any] | None:
    """Найти пользователя по реферальному коду."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM users WHERE referral_code = ?", (code,)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)


def generate_referral_code() -> str:
    """Генерация уникального реферального кода."""
    return uuid.uuid4().hex[:8]


async def get_referral_count(referral_code: str) -> int:
    """Количество пользователей, пришедших по реферальной ссылке."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM users WHERE referred_by = ?",
        (referral_code,),
    )
    row = await cursor.fetchone()
    return row["cnt"] if row else 0  # type: ignore[index]


# --- Alerts ---


async def add_alert(user_id: int, keyword: str, max_price: float | None = None) -> int:
    """Добавить алерт."""
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO alerts (user_id, keyword, max_price) VALUES (?, ?, ?)",
        (user_id, keyword, max_price),
    )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


async def get_user_alerts(user_id: int) -> list[dict[str, Any]]:
    """Получить алерты пользователя."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM alerts WHERE user_id = ? AND is_active = 1", (user_id,)
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def delete_alert(alert_id: int) -> None:
    """Деактивировать алерт."""
    db = await get_db()
    await db.execute(
        "UPDATE alerts SET is_active = 0 WHERE id = ?", (alert_id,)
    )
    await db.commit()


async def get_alert_by_id(alert_id: int) -> dict[str, Any] | None:
    """Получить алерт по ID."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM alerts WHERE id = ?", (alert_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)


async def get_active_alerts_for_keyword(keyword: str) -> list[dict[str, Any]]:
    """Получить все активные алерты, ключевое слово которых содержится в тексте.

    Используется для проверки совпадений: возвращает все активные алерты,
    фильтрация по совпадению keyword in product_name делается на уровне Python.
    """
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM alerts WHERE is_active = 1",
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# --- Seller Monitors ---


async def add_seller_monitor(
    user_id: int, competitor_url: str, marketplace: str
) -> int:
    """Добавить мониторинг конкурента."""
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO seller_monitors (user_id, competitor_url, marketplace) VALUES (?, ?, ?)",
        (user_id, competitor_url, marketplace),
    )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


async def get_user_monitors(user_id: int) -> list[dict[str, Any]]:
    """Получить мониторы конкурентов для пользователя."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM seller_monitors WHERE user_id = ?", (user_id,)
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def delete_seller_monitor(monitor_id: int) -> None:
    """Удалить мониторинг конкурента."""
    db = await get_db()
    await db.execute(
        "DELETE FROM seller_monitors WHERE id = ?", (monitor_id,)
    )
    await db.commit()


async def get_seller_monitor_by_id(monitor_id: int) -> dict[str, Any] | None:
    """Получить монитор конкурента по ID."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM seller_monitors WHERE id = ?", (monitor_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)


async def get_top_referrers(limit: int = 5) -> list[dict[str, Any]]:
    """Получить топ рефереров по количеству приглашений."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT u.telegram_id, u.username, COUNT(r.id) as count "
        "FROM users u JOIN users r ON r.referred_by = u.referral_code "
        "GROUP BY u.id ORDER BY count DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# --- Posts ---


async def add_post(product_id: int, channel_id: int, text: str) -> int:
    """Добавить запись о публикации."""
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO posts (product_id, channel_id, text) VALUES (?, ?, ?)",
        (product_id, channel_id, text),
    )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]
