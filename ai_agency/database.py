"""Асинхронная работа с SQLite базой данных для AI-агентства."""

import aiosqlite
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

import config


async def get_connection() -> aiosqlite.Connection:
    """Получить подключение к БД."""
    conn = await aiosqlite.connect(config.DATABASE_PATH)
    conn.row_factory = aiosqlite.Row
    return conn


async def init_db() -> None:
    """Инициализация базы данных: создание таблиц."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                registered_at TEXT NOT NULL DEFAULT (datetime('now')),
                total_spent REAL NOT NULL DEFAULT 0.0,
                balance REAL NOT NULL DEFAULT 0.0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                service_type TEXT NOT NULL,
                input_text TEXT NOT NULL,
                output_text TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                completed_at TEXT,
                price REAL NOT NULL DEFAULT 0.0,
                FOREIGN KEY (client_id) REFERENCES clients(telegram_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                method TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (client_id) REFERENCES clients(telegram_id)
            )
        """)
        await db.commit()


# --- Клиенты ---

async def get_or_create_client(
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> dict:
    """Получить клиента или создать нового."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM clients WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)

        await db.execute(
            "INSERT INTO clients (telegram_id, username, first_name) VALUES (?, ?, ?)",
            (telegram_id, username, first_name),
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT * FROM clients WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        return dict(row)


async def get_client_balance(telegram_id: int) -> float:
    """Получить баланс клиента."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT balance FROM clients WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0.0


async def update_balance(telegram_id: int, new_balance: float) -> None:
    """Обновить баланс клиента."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE clients SET balance = ? WHERE telegram_id = ?",
            (new_balance, telegram_id),
        )
        await db.commit()


async def update_total_spent(telegram_id: int, amount: float) -> None:
    """Увеличить общую сумму расходов клиента."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE clients SET total_spent = total_spent + ? WHERE telegram_id = ?",
            (amount, telegram_id),
        )
        await db.commit()


async def get_all_clients() -> List[dict]:
    """Получить список всех клиентов."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM clients ORDER BY registered_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# --- Заказы ---

async def create_order(
    client_id: int,
    service_type: str,
    input_text: str,
    price: float,
) -> int:
    """Создать новый заказ, вернуть ID."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO orders (client_id, service_type, input_text, price, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (client_id, service_type, input_text, price),
        )
        await db.commit()
        return cursor.lastrowid


async def update_order_status(
    order_id: int,
    status: str,
    output_text: Optional[str] = None,
) -> None:
    """Обновить статус заказа."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        if output_text is not None:
            await db.execute(
                """UPDATE orders SET status = ?, output_text = ?,
                   completed_at = datetime('now') WHERE id = ?""",
                (status, output_text, order_id),
            )
        else:
            await db.execute(
                "UPDATE orders SET status = ? WHERE id = ?",
                (status, order_id),
            )
        await db.commit()


async def get_orders_by_client(client_id: int, limit: int = 10) -> List[dict]:
    """Получить заказы клиента."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM orders WHERE client_id = ? ORDER BY created_at DESC LIMIT ?",
            (client_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_recent_orders(limit: int = 20) -> List[dict]:
    """Получить последние заказы."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_stats_for_period(days: int) -> Tuple[int, float]:
    """Получить статистику за период: (количество заказов, выручка)."""
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """SELECT COUNT(*) as cnt, COALESCE(SUM(price), 0) as revenue
               FROM orders WHERE created_at >= ? AND status = 'completed'""",
            (since,),
        )
        row = await cursor.fetchone()
        return (row[0], row[1]) if row else (0, 0.0)


# --- Платежи ---

async def add_payment(client_id: int, amount: float, method: str = "manual") -> int:
    """Добавить запись о платеже."""
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO payments (client_id, amount, method) VALUES (?, ?, ?)",
            (client_id, amount, method),
        )
        await db.commit()
        return cursor.lastrowid
