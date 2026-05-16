"""SQLite-хранилище для Lead Scoring.

Таблица lead_scores хранит оценки заказов с фриланс-площадок.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.getenv("LEAD_SCORING_DB_PATH", "lead_scoring.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    """Создать таблицу lead_scores, если не существует. Идемпотентно."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lead_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                tg_id INTEGER NOT NULL DEFAULT 0,
                score INTEGER NOT NULL DEFAULT 0,
                factors_json TEXT NOT NULL DEFAULT '{}',
                scored_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_score(
    order_id: str, tg_id: int, score: int, factors: dict
) -> int:
    """Сохранить оценку лида. Возвращает id записи."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT OR REPLACE INTO lead_scores (order_id, tg_id, score, factors_json, scored_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (order_id, tg_id, score, json.dumps(factors, ensure_ascii=False), _now_iso()),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]


def get_score(order_id: str) -> Optional[dict]:
    """Получить оценку по order_id."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM lead_scores WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["factors"] = json.loads(result.pop("factors_json", "{}"))
        return result


def get_top_leads(limit: int = 10, min_score: int = 0) -> list[dict]:
    """Получить топ лидов, отсортированных по score DESC."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM lead_scores
            WHERE score >= ?
            ORDER BY score DESC
            LIMIT ?
            """,
            (min_score, limit),
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["factors"] = json.loads(d.pop("factors_json", "{}"))
            results.append(d)
        return results


def get_scores_above(threshold: int) -> list[dict]:
    """Получить все лиды с оценкой выше threshold."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM lead_scores
            WHERE score >= ?
            ORDER BY score DESC
            """,
            (threshold,),
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["factors"] = json.loads(d.pop("factors_json", "{}"))
            results.append(d)
        return results
