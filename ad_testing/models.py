"""SQLite-хранилище для A/B-тестирования рекламных каналов.

Таблицы:
  - ad_channels:     каналы с метриками (показы, клики, конверсии, расход, доход).
  - ab_experiments:  эксперименты сравнения двух каналов.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional


DB_PATH = os.getenv("AD_TESTING_DB_PATH", "ad_testing.db")


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
            CREATE TABLE IF NOT EXISTS ad_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                source_tag TEXT UNIQUE NOT NULL,
                impressions INTEGER NOT NULL DEFAULT 0,
                clicks INTEGER NOT NULL DEFAULT 0,
                conversions INTEGER NOT NULL DEFAULT 0,
                spend REAL NOT NULL DEFAULT 0,
                revenue REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ab_experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_a_id INTEGER NOT NULL,
                channel_b_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                started_at TEXT NOT NULL,
                ended_at TEXT,
                winner TEXT
            )
            """
        )
        conn.commit()


def register_channel(name: str, source_tag: str) -> int:
    """Зарегистрировать рекламный канал. Возвращает id."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO ad_channels (name, source_tag, created_at)
            VALUES (?, ?, ?)
            """,
            (name, source_tag, _now_iso()),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]


def record_event(source_tag: str, event_type: str, revenue: float = 0.0) -> None:
    """Записать событие для канала: click, conversion, impression."""
    with _connect() as conn:
        if event_type == "click":
            conn.execute(
                "UPDATE ad_channels SET clicks = clicks + 1 WHERE source_tag = ?",
                (source_tag,),
            )
        elif event_type == "conversion":
            conn.execute(
                """
                UPDATE ad_channels
                SET conversions = conversions + 1, revenue = revenue + ?
                WHERE source_tag = ?
                """,
                (float(revenue), source_tag),
            )
        elif event_type == "impression":
            conn.execute(
                "UPDATE ad_channels SET impressions = impressions + 1 WHERE source_tag = ?",
                (source_tag,),
            )
        conn.commit()


def record_impression(source_tag: str, count: int = 1) -> None:
    """Записать показы для канала."""
    with _connect() as conn:
        conn.execute(
            "UPDATE ad_channels SET impressions = impressions + ? WHERE source_tag = ?",
            (int(count), source_tag),
        )
        conn.commit()


def get_channel_stats(source_tag: str) -> Optional[dict]:
    """Статистика канала по source_tag."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM ad_channels WHERE source_tag = ?",
            (source_tag,),
        ).fetchone()
        return dict(row) if row else None


def list_channels() -> list[dict]:
    """Список всех каналов с метриками."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM ad_channels ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_channel_by_tag(source_tag: str) -> Optional[dict]:
    """Получить канал по source_tag (алиас для get_channel_stats)."""
    return get_channel_stats(source_tag)
