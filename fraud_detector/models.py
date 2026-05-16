"""SQLite storage for fraud detection scores."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from logging_config import get_logger

log = get_logger(__name__)

DB_PATH = os.getenv("FRAUD_DB_PATH", "fraud.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    """Create fraud_scores table if not exists. Idempotent."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fraud_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                score INTEGER NOT NULL,
                flags_json TEXT NOT NULL DEFAULT '[]',
                checked_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_fraud_score(order_id: str, score: int, flags: list[str]) -> None:
    """Save a fraud score for an order."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO fraud_scores (order_id, score, flags_json, checked_at)
            VALUES (?, ?, ?, ?)
            """,
            (order_id, score, json.dumps(flags, ensure_ascii=False), _now_iso()),
        )
        conn.commit()
    log.info("fraud_score_saved", order_id=order_id, score=score)


def get_fraud_score(order_id: str) -> Optional[dict]:
    """Get fraud score for an order."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM fraud_scores WHERE order_id = ? ORDER BY id DESC LIMIT 1",
            (order_id,),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["flags"] = json.loads(result.pop("flags_json"))
        return result


def get_flagged_orders(min_score: int = 70) -> list[dict]:
    """Get all orders with fraud score above threshold."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM fraud_scores WHERE score >= ? ORDER BY score DESC",
            (min_score,),
        ).fetchall()
        results = []
        for row in rows:
            r = dict(row)
            r["flags"] = json.loads(r.pop("flags_json"))
            results.append(r)
        return results
