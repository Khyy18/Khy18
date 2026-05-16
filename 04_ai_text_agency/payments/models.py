"""SQLite-хранилище платёжных данных (invoices, payment_history).

Путь к БД: переменная окружения PAYMENTS_DB_PATH или 'payments.db' по умолчанию.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional


DB_PATH = os.getenv("PAYMENTS_DB_PATH", "payments.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    """Создать таблицы invoices и payment_history. Идемпотентно."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_tg_id INTEGER NOT NULL,
                amount_stars INTEGER NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                paid_at TEXT,
                telegram_payment_charge_id TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                user_tg_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                currency TEXT NOT NULL DEFAULT 'XTR',
                provider TEXT NOT NULL DEFAULT 'telegram_stars',
                completed_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def create_invoice(user_tg_id: int, amount_stars: int, description: str) -> int:
    """Создать запись инвойса. Возвращает invoice_id."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO invoices (user_tg_id, amount_stars, description, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (user_tg_id, amount_stars, description, _now_iso()),
        )
        conn.commit()
        return cur.lastrowid


def mark_paid(invoice_id: int, telegram_charge_id: str) -> bool:
    """Отметить инвойс как оплаченный. Возвращает True если запись найдена."""
    now = _now_iso()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE invoices
            SET status = 'paid', paid_at = ?, telegram_payment_charge_id = ?
            WHERE id = ? AND status = 'pending'
            """,
            (now, telegram_charge_id, invoice_id),
        )
        if cur.rowcount == 0:
            return False
        # Записываем в историю платежей
        row = conn.execute(
            "SELECT user_tg_id, amount_stars FROM invoices WHERE id = ?",
            (invoice_id,),
        ).fetchone()
        if row:
            conn.execute(
                """
                INSERT INTO payment_history
                    (invoice_id, user_tg_id, amount, currency, provider, completed_at)
                VALUES (?, ?, ?, 'XTR', 'telegram_stars', ?)
                """,
                (invoice_id, row["user_tg_id"], row["amount_stars"], now),
            )
        conn.commit()
        return True


def get_invoice(invoice_id: int) -> Optional[dict]:
    """Получить инвойс по id."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        return dict(row) if row else None


def get_user_payments(user_tg_id: int) -> list[dict]:
    """Получить историю завершённых платежей пользователя."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM payment_history
            WHERE user_tg_id = ?
            ORDER BY id DESC
            """,
            (user_tg_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_pending_invoice(user_tg_id: int) -> Optional[dict]:
    """Получить последний незавершённый инвойс пользователя."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM invoices
            WHERE user_tg_id = ? AND status = 'pending'
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_tg_id,),
        ).fetchone()
        return dict(row) if row else None
