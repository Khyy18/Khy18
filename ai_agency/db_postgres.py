"""PostgreSQL database backend with asyncpg. Same interface as database.py."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import config

# Graceful import
try:
    import asyncpg
except ImportError:
    asyncpg = None

try:
    import aiosqlite
except ImportError:
    aiosqlite = None

logger = logging.getLogger(__name__)

_pool: Optional["asyncpg.Pool"] = None


async def init_db() -> None:
    """Create connection pool and initialize all tables."""
    global _pool

    if asyncpg is None:
        logger.error("asyncpg not installed. Cannot use PostgreSQL backend.")
        return

    if not config.DATABASE_URL:
        logger.error("DATABASE_URL not set. Cannot connect to PostgreSQL.")
        return

    _pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=2, max_size=10)

    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                telegram_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                registered_at TIMESTAMP NOT NULL DEFAULT NOW(),
                total_spent DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                balance DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                referred_by BIGINT,
                last_notified_at TIMESTAMP,
                last_upsell_at TIMESTAMP,
                free_trial_used INTEGER NOT NULL DEFAULT 0,
                language TEXT NOT NULL DEFAULT 'ru',
                loyalty_notified_level TEXT DEFAULT 'bronze'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                client_id BIGINT NOT NULL REFERENCES clients(telegram_id),
                service_type TEXT NOT NULL,
                input_text TEXT NOT NULL,
                output_text TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMP,
                price DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                rating INTEGER,
                ab_variant_id INTEGER,
                case_posted INTEGER NOT NULL DEFAULT 0
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                client_id BIGINT NOT NULL REFERENCES clients(telegram_id),
                amount DOUBLE PRECISION NOT NULL,
                method TEXT NOT NULL DEFAULT 'manual',
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                referrer_id BIGINT NOT NULL REFERENCES clients(telegram_id),
                referred_id BIGINT NOT NULL REFERENCES clients(telegram_id),
                bonus_amount DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                paid INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                client_id BIGINT NOT NULL REFERENCES clients(telegram_id),
                tier TEXT NOT NULL DEFAULT 'none',
                status TEXT NOT NULL DEFAULT 'active',
                started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMP,
                orders_used INTEGER NOT NULL DEFAULT 0,
                yookassa_subscription_id TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_payments (
                payment_id TEXT PRIMARY KEY,
                processed_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)

    logger.info("PostgreSQL database initialized successfully.")


async def close_db() -> None:
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def get_or_create_client(
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> dict:
    """Get client or create a new one."""
    if not _pool:
        return {}
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM clients WHERE telegram_id = $1", telegram_id
        )
        if row:
            return dict(row)
        await conn.execute(
            "INSERT INTO clients (telegram_id, username, first_name) VALUES ($1, $2, $3) "
            "ON CONFLICT (telegram_id) DO NOTHING",
            telegram_id, username, first_name,
        )
        row = await conn.fetchrow(
            "SELECT * FROM clients WHERE telegram_id = $1", telegram_id
        )
        return dict(row) if row else {}


async def create_order(
    client_id: int,
    service_type: str,
    input_text: str,
    price: float,
) -> int:
    """Create a new order, return its ID."""
    if not _pool:
        return 0
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO orders (client_id, service_type, input_text, price, status)
               VALUES ($1, $2, $3, $4, 'pending') RETURNING id""",
            client_id, service_type, input_text, price,
        )
        return row["id"] if row else 0


async def update_order_status(
    order_id: int,
    status: str,
    output_text: Optional[str] = None,
) -> None:
    """Update order status."""
    if not _pool:
        return
    async with _pool.acquire() as conn:
        if output_text is not None:
            await conn.execute(
                """UPDATE orders SET status = $1, output_text = $2,
                   completed_at = NOW() WHERE id = $3""",
                status, output_text, order_id,
            )
        else:
            await conn.execute(
                "UPDATE orders SET status = $1 WHERE id = $2",
                status, order_id,
            )


async def get_client_balance(telegram_id: int) -> float:
    """Get client balance."""
    if not _pool:
        return 0.0
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT balance FROM clients WHERE telegram_id = $1", telegram_id
        )
        return row["balance"] if row else 0.0


async def get_order_by_id(order_id: int) -> Optional[dict]:
    """Get order by ID."""
    if not _pool:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM orders WHERE id = $1", order_id
        )
        return dict(row) if row else None


async def get_orders_by_client(client_id: int, limit: int = 10) -> List[dict]:
    """Get orders for a client."""
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM orders WHERE client_id = $1 ORDER BY created_at DESC LIMIT $2",
            client_id, limit,
        )
        return [dict(row) for row in rows]


async def add_payment(client_id: int, amount: float, method: str = "manual") -> int:
    """Add payment record."""
    if not _pool:
        return 0
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO payments (client_id, amount, method) VALUES ($1, $2, $3) RETURNING id",
            client_id, amount, method,
        )
        return row["id"] if row else 0


async def get_client_order_count(client_id: int) -> int:
    """Get order count for a client."""
    if not _pool:
        return 0
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) as cnt FROM orders WHERE client_id = $1", client_id
        )
        return row["cnt"] if row else 0


async def migrate_sqlite_to_postgres(sqlite_path: str) -> None:
    """Migrate all data from SQLite database to PostgreSQL."""
    if not _pool:
        logger.error("PostgreSQL pool not initialized.")
        return
    if aiosqlite is None:
        logger.error("aiosqlite not installed, cannot read SQLite database.")
        return

    logger.info("Starting migration from SQLite (%s) to PostgreSQL...", sqlite_path)

    async with aiosqlite.connect(sqlite_path) as db:
        db.row_factory = aiosqlite.Row

        # Migrate clients
        cursor = await db.execute("SELECT * FROM clients")
        clients = await cursor.fetchall()
        async with _pool.acquire() as conn:
            for row in clients:
                row_dict = dict(row)
                await conn.execute(
                    """INSERT INTO clients (telegram_id, username, first_name,
                       total_spent, balance, referred_by, free_trial_used, language)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                       ON CONFLICT (telegram_id) DO NOTHING""",
                    row_dict["telegram_id"],
                    row_dict.get("username"),
                    row_dict.get("first_name"),
                    row_dict.get("total_spent", 0.0),
                    row_dict.get("balance", 0.0),
                    row_dict.get("referred_by"),
                    row_dict.get("free_trial_used", 0),
                    row_dict.get("language", "ru"),
                )

        # Migrate orders
        cursor = await db.execute("SELECT * FROM orders")
        orders = await cursor.fetchall()
        async with _pool.acquire() as conn:
            for row in orders:
                row_dict = dict(row)
                await conn.execute(
                    """INSERT INTO orders (id, client_id, service_type, input_text,
                       output_text, status, price, rating)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                       ON CONFLICT (id) DO NOTHING""",
                    row_dict["id"],
                    row_dict["client_id"],
                    row_dict["service_type"],
                    row_dict["input_text"],
                    row_dict.get("output_text"),
                    row_dict.get("status", "pending"),
                    row_dict.get("price", 0.0),
                    row_dict.get("rating"),
                )

        # Migrate payments
        cursor = await db.execute("SELECT * FROM payments")
        payments = await cursor.fetchall()
        async with _pool.acquire() as conn:
            for row in payments:
                row_dict = dict(row)
                await conn.execute(
                    """INSERT INTO payments (id, client_id, amount, method)
                       VALUES ($1, $2, $3, $4)
                       ON CONFLICT (id) DO NOTHING""",
                    row_dict["id"],
                    row_dict["client_id"],
                    row_dict["amount"],
                    row_dict.get("method", "manual"),
                )

    logger.info("Migration from SQLite to PostgreSQL completed.")
