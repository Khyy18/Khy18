"""SQLite database schema initialization with aiosqlite."""

import aiosqlite

DB_PATH = "data/exchanger.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    exchanges_count INTEGER DEFAULT 0,
    total_volume REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS exchanges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    from_currency TEXT NOT NULL,
    to_currency TEXT NOT NULL,
    amount REAL NOT NULL,
    estimated_amount REAL,
    exchange_id TEXT,
    provider TEXT NOT NULL,
    status TEXT DEFAULT 'new',
    deposit_address TEXT,
    payout_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    markup_amount REAL DEFAULT 0.0,
    fixed_rate_id TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_exchanges_user_id ON exchanges(user_id);
CREATE INDEX IF NOT EXISTS idx_exchanges_status ON exchanges(status);
CREATE INDEX IF NOT EXISTS idx_exchanges_created_at ON exchanges(created_at);
"""


async def init_db() -> None:
    """Initialize database and create tables."""
    import os

    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def get_db() -> aiosqlite.Connection:
    """Get a database connection."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db
