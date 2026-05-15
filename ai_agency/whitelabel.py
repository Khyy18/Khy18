"""White-label B2B система: управление партнёрскими ботами."""

import json
import logging
from datetime import datetime
from typing import List, Optional

import aiosqlite

import config
import database

logger = logging.getLogger(__name__)


async def init_whitelabel_tables() -> None:
    """Создать таблицы для white-label системы."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS whitelabel_bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                token TEXT NOT NULL,
                bot_name TEXT NOT NULL,
                persona TEXT NOT NULL DEFAULT 'Assistant',
                allowed_services TEXT NOT NULL DEFAULT '[]',
                pricing_multiplier REAL NOT NULL DEFAULT 1.0,
                revenue_share REAL NOT NULL DEFAULT 0.3,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS whitelabel_revenue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id INTEGER NOT NULL,
                order_id INTEGER,
                amount REAL NOT NULL,
                owner_share REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (bot_id) REFERENCES whitelabel_bots(id)
            )
        """)
        await db.commit()


async def create_whitelabel_bot(
    owner_id: int,
    token: str,
    bot_name: str,
    persona: str = "Assistant",
    allowed_services: Optional[List[str]] = None,
    pricing_multiplier: float = 1.0,
    revenue_share: float = 0.3,
) -> int:
    """Создать запись white-label бота."""
    services_json = json.dumps(allowed_services or [])
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO whitelabel_bots
               (owner_id, token, bot_name, persona, allowed_services,
                pricing_multiplier, revenue_share, active)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (owner_id, token, bot_name, persona, services_json,
             pricing_multiplier, revenue_share),
        )
        await db.commit()
        return cursor.lastrowid


async def get_whitelabel_bots(active_only: bool = True) -> List[dict]:
    """Получить список white-label ботов."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM whitelabel_bots"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY created_at DESC"
        cursor = await db.execute(query)
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            bot_data = dict(row)
            bot_data["allowed_services"] = json.loads(
                bot_data.get("allowed_services", "[]")
            )
            result.append(bot_data)
        return result


async def get_whitelabel_stats(bot_id: int) -> dict:
    """Получить статистику white-label бота."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT COUNT(*) as total_orders,
                      COALESCE(SUM(amount), 0) as total_revenue,
                      COALESCE(SUM(owner_share), 0) as total_owner_share
               FROM whitelabel_revenue WHERE bot_id = ?""",
            (bot_id,),
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return {"total_orders": 0, "total_revenue": 0, "total_owner_share": 0}


async def record_whitelabel_revenue(
    bot_id: int,
    order_id: int,
    amount: float,
    revenue_share: float = 0.3,
) -> None:
    """Записать доход от white-label бота."""
    owner_share = amount * revenue_share
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            """INSERT INTO whitelabel_revenue (bot_id, order_id, amount, owner_share)
               VALUES (?, ?, ?, ?)""",
            (bot_id, order_id, amount, owner_share),
        )
        await db.commit()


async def deactivate_bot(bot_id: int) -> None:
    """Деактивировать white-label бота."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE whitelabel_bots SET active = 0 WHERE id = ?",
            (bot_id,),
        )
        await db.commit()
