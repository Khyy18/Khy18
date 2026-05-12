"""Хранилище состояния торгового бота на SQLite (stdlib sqlite3).

Две таблицы:
  - trades:           история сделок, их результат и контекст индикаторов.
  - rejected_signals: сигналы, которые ИИ-аналитик отклонил (для кнопки
                      «ПОЧЕМУ МИМО?» и для обратной связи в следующих промптах).

Функции get_recent_errors(limit=5) и get_last_rejection() используются
в ai_analyst.decide(...) и в Telegram-хэндлерах.
Инициализация таблиц выполняется при импорте модуля (init_db()).
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trades.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    """Создать таблицы, если их ещё нет."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry REAL NOT NULL,
                    exit REAL,
                    qty REAL NOT NULL,
                    pnl REAL,
                    ema REAL,
                    rsi REAL,
                    atr REAL,
                    ai_reason TEXT,
                    outcome TEXT NOT NULL DEFAULT 'OPEN'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rejected_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    reason TEXT,
                    confidence INTEGER,
                    context_json TEXT
                )
                """
            )
            conn.commit()
        print(f"[MEMORY] База данных trades.db инициализирована: {DB_PATH}")
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка инициализации БД: {exc}")


def record_trade(
    symbol: str,
    side: str,
    entry: float,
    qty: float,
    ema_val: Optional[float] = None,
    rsi_val: Optional[float] = None,
    atr_val: Optional[float] = None,
    ai_reason: Optional[str] = None,
    outcome: str = "OPEN",
) -> Optional[int]:
    """Сохранить открытую сделку. Возвращает id созданной записи."""
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO trades
                    (ts, symbol, side, entry, qty, ema, rsi, atr, ai_reason, outcome)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    symbol,
                    side,
                    float(entry),
                    float(qty),
                    ema_val,
                    rsi_val,
                    atr_val,
                    ai_reason,
                    outcome,
                ),
            )
            conn.commit()
            return cur.lastrowid
    except sqlite3.Error as exc:
        print(f"[MEMORY] Не удалось записать сделку: {exc}")
        return None


def update_trade_outcome(
    trade_id: int,
    exit_price: float,
    pnl: float,
    outcome: str,
) -> None:
    """Обновить результат сделки (WIN/LOSS/OPEN)."""
    try:
        with _connect() as conn:
            conn.execute(
                "UPDATE trades SET exit = ?, pnl = ?, outcome = ? WHERE id = ?",
                (float(exit_price), float(pnl), outcome, int(trade_id)),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[MEMORY] Не удалось обновить сделку #{trade_id}: {exc}")


def record_rejection(
    reason: str,
    confidence: int,
    ctx: dict[str, Any],
) -> None:
    """Сохранить отклонённый ИИ сигнал для дальнейшего разбора."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO rejected_signals (ts, reason, confidence, context_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    reason,
                    int(confidence),
                    json.dumps(ctx, ensure_ascii=False),
                ),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[MEMORY] Не удалось записать отклонённый сигнал: {exc}")


def get_recent_errors(limit: int = 5) -> list[dict[str, Any]]:
    """Последние `limit` убыточных сделок (outcome='LOSS') для передачи в Gemini."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, symbol, side, entry, exit, qty, pnl, ema, rsi, atr, ai_reason, outcome
                FROM trades
                WHERE outcome = 'LOSS'
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка чтения последних ошибок: {exc}")
        return []


def get_last_rejection() -> Optional[dict[str, Any]]:
    """Последний отклонённый ИИ сигнал - для кнопки «ПОЧЕМУ МИМО?»."""
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT id, ts, reason, confidence, context_json
                FROM rejected_signals
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            try:
                data["context"] = json.loads(data.pop("context_json") or "{}")
            except json.JSONDecodeError:
                data["context"] = {}
            return data
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка чтения последнего отклонения: {exc}")
        return None


def get_open_trades() -> list[dict[str, Any]]:
    """Список сделок со статусом OPEN (для кнопки ПОЗИЦИИ в Telegram)."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, symbol, side, entry, qty, ema, rsi, atr, ai_reason
                FROM trades
                WHERE outcome = 'OPEN'
                ORDER BY id DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка чтения открытых сделок: {exc}")
        return []


def get_stats() -> dict[str, Any]:
    """Сводная статистика: count, wins, losses, winrate, pnl_sum."""
    stats = {
        "count": 0,
        "wins": 0,
        "losses": 0,
        "winrate": 0.0,
        "pnl_sum": 0.0,
    }
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*)                                       AS count,
                    SUM(CASE WHEN outcome='WIN'  THEN 1 ELSE 0 END) AS wins,
                    SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) AS losses,
                    COALESCE(SUM(pnl), 0)                          AS pnl_sum
                FROM trades
                WHERE outcome IN ('WIN','LOSS')
                """
            ).fetchone()
            if row is not None:
                count = int(row["count"] or 0)
                wins = int(row["wins"] or 0)
                losses = int(row["losses"] or 0)
                stats["count"] = count
                stats["wins"] = wins
                stats["losses"] = losses
                stats["pnl_sum"] = float(row["pnl_sum"] or 0.0)
                total = wins + losses
                stats["winrate"] = (wins / total * 100.0) if total else 0.0
    except sqlite3.Error as exc:
        print(f"[MEMORY] Ошибка чтения статистики: {exc}")
    return stats


# Инициализируем схему при первом импорте модуля.
init_db()
