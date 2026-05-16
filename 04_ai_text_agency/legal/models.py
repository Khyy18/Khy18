"""SQLite-хранилище договоров-оферт."""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.getenv("LEGAL_DB_PATH", "legal.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Создание таблицы offers если не существует."""
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_tg_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            amount REAL NOT NULL,
            service_description TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            accepted_at TEXT,
            pdf_path TEXT,
            offer_number TEXT UNIQUE NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def create_offer_record(user_tg_id: int, user_name: str, amount: float,
                        description: str) -> int:
    """Создать запись оферты, вернуть offer_id."""
    conn = _connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")

    # Получаем следующий порядковый номер за сегодня
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM offers WHERE offer_number LIKE ?",
        (f"ZC-{date_part}-%",)
    ).fetchone()
    seq = (row["cnt"] if row else 0) + 1
    offer_number = f"ZC-{date_part}-{seq:04d}"

    cursor = conn.execute(
        """INSERT INTO offers (user_tg_id, user_name, amount, service_description,
                              generated_at, offer_number)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_tg_id, user_name, amount, description, now, offer_number)
    )
    offer_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return offer_id


def mark_accepted(offer_id: int) -> bool:
    """Пометить оферту как акцептованную (оплата = акцепт)."""
    conn = _connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.execute(
        "UPDATE offers SET accepted_at = ? WHERE id = ?",
        (now, offer_id)
    )
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def get_user_offers(user_tg_id: int) -> list[dict]:
    """Получить все оферты пользователя."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM offers WHERE user_tg_id = ? ORDER BY id DESC",
        (user_tg_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def is_first_payment(user_tg_id: int) -> bool:
    """True если у пользователя нет ранее акцептованных оферт."""
    conn = _connect()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM offers WHERE user_tg_id = ? AND accepted_at IS NOT NULL",
        (user_tg_id,)
    ).fetchone()
    conn.close()
    return row["cnt"] == 0


def get_offer(offer_id: int) -> Optional[dict]:
    """Получить оферту по ID."""
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM offers WHERE id = ?",
        (offer_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None
