"""Аутентификация и rate-limiting для REST API."""

import uuid
from datetime import datetime, date
from typing import Optional

import aiosqlite
from fastapi import Header, HTTPException

import config


async def init_api_tables() -> None:
    """Создать таблицу api_keys если не существует."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                client_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                rate_limit INTEGER NOT NULL DEFAULT 60,
                requests_today INTEGER NOT NULL DEFAULT 0,
                last_reset TEXT
            )
        """)
        await db.commit()


async def validate_api_key(key: str) -> Optional[dict]:
    """
    Проверить API-ключ и rate limit.

    Возвращает dict с информацией о клиенте или None если ключ невалиден/лимит превышен.
    """
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM api_keys WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        if not row:
            return None

        api_key = dict(row)
        today_str = date.today().isoformat()

        # Сбрасываем счетчик если новый день
        if api_key.get("last_reset") != today_str:
            await db.execute(
                "UPDATE api_keys SET requests_today = 0, last_reset = ? WHERE id = ?",
                (today_str, api_key["id"]),
            )
            await db.commit()
            api_key["requests_today"] = 0

        # Проверяем rate limit
        if api_key["requests_today"] >= api_key["rate_limit"]:
            return None

        # Инкрементируем счетчик
        await db.execute(
            "UPDATE api_keys SET requests_today = requests_today + 1 WHERE id = ?",
            (api_key["id"],),
        )
        await db.commit()

        return api_key


async def create_api_key(client_id: int, rate_limit: int = 60) -> str:
    """
    Создать новый API-ключ для клиента.

    Args:
        client_id: ID клиента
        rate_limit: лимит запросов в день

    Returns:
        Сгенерированный API-ключ (uuid4)
    """
    key = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO api_keys (key, client_id, created_at, rate_limit, last_reset)
               VALUES (?, ?, ?, ?, ?)""",
            (key, client_id, now, rate_limit, date.today().isoformat()),
        )
        await db.commit()
    return key


async def get_current_client(x_api_key: str = Header()) -> dict:
    """
    FastAPI Depends: валидация API-ключа из заголовка X-API-Key.

    Raises:
        HTTPException 401: если ключ не найден
        HTTPException 429: если превышен rate limit
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")

    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Сбрасываем счетчик если новый день (атомарно)
        today_str = date.today().isoformat()
        await db.execute(
            "UPDATE api_keys SET requests_today = 0, last_reset = ? WHERE key = ? AND last_reset != ?",
            (today_str, x_api_key, today_str),
        )

        # Атомарный инкремент с проверкой rate limit (устраняет TOCTOU)
        cursor = await db.execute(
            "UPDATE api_keys SET requests_today = requests_today + 1 WHERE key = ? AND requests_today < rate_limit",
            (x_api_key,),
        )
        if cursor.rowcount == 0:
            # Либо ключ не существует, либо лимит превышен
            check_cursor = await db.execute(
                "SELECT * FROM api_keys WHERE key = ?", (x_api_key,)
            )
            row = await check_cursor.fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="Invalid API key")
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        await db.commit()

        # Получаем данные ключа для возврата
        cursor = await db.execute(
            "SELECT * FROM api_keys WHERE key = ?", (x_api_key,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid API key")

    return dict(row)
