"""Инициализация базы данных и создание таблиц."""

import aiosqlite

from bot.config import settings


async def init_db() -> None:
    """Создает все таблицы в SQLite, если они не существуют."""
    db = await aiosqlite.connect(settings.db_path)
    try:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marketplace TEXT NOT NULL,
                external_id TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT,
                brand TEXT,
                url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                price REAL NOT NULL,
                old_price REAL,
                discount_percent REAL,
                is_fraud INTEGER DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                is_vip INTEGER DEFAULT 0,
                vip_expires_at TEXT,
                interests TEXT DEFAULT '[]',
                referral_code TEXT UNIQUE,
                referred_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                keyword TEXT NOT NULL,
                max_price REAL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS seller_monitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                competitor_url TEXT NOT NULL,
                marketplace TEXT NOT NULL,
                last_check TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                clicks INTEGER DEFAULT 0,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)

        await db.commit()
    finally:
        await db.close()
