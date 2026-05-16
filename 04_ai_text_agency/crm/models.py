"""SQLite-хранилище CRM: клиенты и воронка.

Таблица 'clients' хранит клиентов с этапами воронки:
lead -> trial -> paid -> churned.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from logging_config import get_logger

log = get_logger(__name__)

DB_PATH = os.getenv("CRM_DB_PATH", "crm.db")

VALID_STAGES = ("lead", "trial", "paid", "churned")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    """Создать таблицы, если не существуют. Идемпотентно."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER UNIQUE NOT NULL,
                name TEXT NOT NULL,
                stage TEXT NOT NULL DEFAULT 'lead',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                notes TEXT DEFAULT ''
            )
            """
        )
        conn.commit()


def create_client(tg_id: int, name: str) -> int:
    """Создать клиента. Возвращает id."""
    now = _now_iso()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO clients (tg_id, name, stage, created_at, updated_at)
            VALUES (?, ?, 'lead', ?, ?)
            """,
            (tg_id, name, now, now),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]


def get_client(tg_id: int) -> Optional[dict]:
    """Получить клиента по tg_id."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM clients WHERE tg_id = ?", (tg_id,)
        ).fetchone()
        return dict(row) if row else None


def update_stage(tg_id: int, new_stage: str) -> bool:
    """Обновить этап воронки клиента. Возвращает True при успехе."""
    if new_stage not in VALID_STAGES:
        return False
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE clients SET stage = ?, updated_at = ? WHERE tg_id = ?",
            (new_stage, _now_iso(), tg_id),
        )
        conn.commit()
        return cur.rowcount > 0


def list_clients_by_stage(stage: str) -> list[dict]:
    """Список клиентов по этапу."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM clients WHERE stage = ? ORDER BY id ASC",
            (stage,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_funnel_stats() -> dict[str, int]:
    """Статистика воронки: количество клиентов на каждом этапе."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT stage, COUNT(*) as cnt FROM clients GROUP BY stage"
        ).fetchall()
        stats = {stage: 0 for stage in VALID_STAGES}
        for row in rows:
            stats[row["stage"]] = row["cnt"]
        return stats
