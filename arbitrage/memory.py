"""Хранилище арбитражного модуля на SQLite.

Таблицы:
  - arbs:         найденные арбитражные возможности
  - bets:         размещённые ставки
  - daily_pnl:    ежедневная статистика прибыли/убытков
  - ai_learnings: выученные правила AI-фильтра

Паттерны взяты из корневого memory.py: _connect(), _now_iso(), row_factory.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


# Путь к SQLite базе арбитража
def _resolve_db_path() -> str:
    env_path = os.getenv("ARB_DB_PATH", "").strip()
    if env_path:
        return env_path
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "arbitrage.db")


DB_PATH: str = _resolve_db_path()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    """Создать таблицы арбитражной БД. Идемпотентно."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS arbs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    sport TEXT NOT NULL,
                    event TEXT NOT NULL,
                    arb_type TEXT NOT NULL,
                    bookmakers_json TEXT,
                    odds_json TEXT,
                    profit_pct REAL,
                    edge_pct REAL,
                    ai_score INTEGER,
                    status TEXT NOT NULL DEFAULT 'FOUND',
                    commence_time TEXT
                )
                """
            )
            # Добавляем commence_time если таблица уже существовала без этого столбца
            try:
                conn.execute(
                    "ALTER TABLE arbs ADD COLUMN commence_time TEXT"
                )
            except sqlite3.OperationalError:
                pass  # столбец уже существует
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    arb_id INTEGER,
                    ts TEXT NOT NULL,
                    bookmaker TEXT NOT NULL,
                    event TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    stake REAL NOT NULL,
                    odds REAL NOT NULL,
                    result TEXT NOT NULL DEFAULT 'PENDING',
                    pnl REAL,
                    FOREIGN KEY (arb_id) REFERENCES arbs(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_pnl (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL UNIQUE,
                    total_staked REAL NOT NULL DEFAULT 0,
                    total_won REAL NOT NULL DEFAULT 0,
                    pnl REAL NOT NULL DEFAULT 0,
                    roi_pct REAL NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_learnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    rule_type TEXT NOT NULL,
                    rule_text TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.5,
                    source TEXT
                )
                """
            )
            conn.commit()
        print(f"[ARB_MEMORY] База данных инициализирована: {DB_PATH}")
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка инициализации БД: {exc}")


def record_arb(
    sport: str,
    event: str,
    arb_type: str,
    bookmakers: list[str],
    odds: dict[str, Any],
    profit_pct: float,
    edge_pct: float,
    ai_score: int = 0,
    status: str = "FOUND",
) -> Optional[int]:
    """Записать найденный арбитраж. Возвращает id записи."""
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO arbs
                    (ts, sport, event, arb_type, bookmakers_json, odds_json,
                     profit_pct, edge_pct, ai_score, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    str(sport),
                    str(event),
                    str(arb_type),
                    json.dumps(bookmakers, ensure_ascii=False),
                    json.dumps(odds, ensure_ascii=False),
                    float(profit_pct),
                    float(edge_pct),
                    int(ai_score),
                    str(status),
                ),
            )
            conn.commit()
            return cur.lastrowid
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Не удалось записать арбитраж: {exc}")
        return None


def record_bet(
    arb_id: Optional[int],
    bookmaker: str,
    event: str,
    outcome: str,
    stake: float,
    odds: float,
    result: str = "PENDING",
    pnl: Optional[float] = None,
) -> Optional[int]:
    """Записать ставку. Возвращает id записи."""
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO bets
                    (arb_id, ts, bookmaker, event, outcome, stake, odds, result, pnl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    arb_id,
                    _now_iso(),
                    str(bookmaker),
                    str(event),
                    str(outcome),
                    float(stake),
                    float(odds),
                    str(result),
                    pnl,
                ),
            )
            conn.commit()
            return cur.lastrowid
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Не удалось записать ставку: {exc}")
        return None


def update_bet_result(bet_id: int, result: str, pnl: float) -> None:
    """Обновить результат ставки (WON/LOST/VOID)."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                UPDATE bets SET result = ?, pnl = ? WHERE id = ?
                """,
                (str(result), float(pnl), int(bet_id)),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Не удалось обновить ставку #{bet_id}: {exc}")


def get_stats() -> dict[str, Any]:
    """Сводная статистика арбитражей и ставок."""
    stats: dict[str, Any] = {
        "total_arbs": 0,
        "executed_arbs": 0,
        "total_bets": 0,
        "won_bets": 0,
        "lost_bets": 0,
        "total_pnl": 0.0,
    }
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status='EXECUTED' THEN 1 ELSE 0 END) AS executed
                FROM arbs
                """
            ).fetchone()
            if row:
                stats["total_arbs"] = int(row["total"] or 0)
                stats["executed_arbs"] = int(row["executed"] or 0)

            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN result='WON' THEN 1 ELSE 0 END) AS won,
                    SUM(CASE WHEN result='LOST' THEN 1 ELSE 0 END) AS lost,
                    COALESCE(SUM(pnl), 0) AS pnl_sum
                FROM bets
                """
            ).fetchone()
            if row:
                stats["total_bets"] = int(row["total"] or 0)
                stats["won_bets"] = int(row["won"] or 0)
                stats["lost_bets"] = int(row["lost"] or 0)
                stats["total_pnl"] = float(row["pnl_sum"] or 0.0)
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения статистики: {exc}")
    return stats


def get_daily_pnl(days: int = 7) -> list[dict[str, Any]]:
    """Получить ежедневную статистику PnL за последние N дней."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, date, total_staked, total_won, pnl, roi_pct
                FROM daily_pnl
                WHERE date >= date('now', ?)
                ORDER BY date DESC
                """,
                (f"-{int(days)} days",),
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения daily_pnl: {exc}")
        return []


def get_active_arbs() -> list[dict[str, Any]]:
    """Получить арбитражи со статусом FOUND (ещё не исполнены)."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, sport, event, arb_type, bookmakers_json,
                       odds_json, profit_pct, edge_pct, ai_score, status
                FROM arbs
                WHERE status = 'FOUND'
                ORDER BY id DESC
                """
            ).fetchall()
            result: list[dict[str, Any]] = []
            for r in rows:
                data = dict(r)
                try:
                    data["bookmakers"] = json.loads(data.pop("bookmakers_json") or "[]")
                except (json.JSONDecodeError, TypeError):
                    data["bookmakers"] = []
                try:
                    data["odds"] = json.loads(data.pop("odds_json") or "{}")
                except (json.JSONDecodeError, TypeError):
                    data["odds"] = {}
                result.append(data)
            return result
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения активных арбитражей: {exc}")
        return []


def get_active_exposure() -> float:
    """Получить текущую экспозицию: сумма stakes по ставкам с result='PENDING'."""
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(stake), 0.0) AS total_staked
                FROM bets
                WHERE result = 'PENDING'
                """
            ).fetchone()
            if row:
                return float(row["total_staked"])
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения экспозиции: {exc}")
    return 0.0


def get_recent_bets(limit: int = 20) -> list[dict[str, Any]]:
    """Получить последние N ставок."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, arb_id, ts, bookmaker, event, outcome,
                       stake, odds, result, pnl
                FROM bets
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения ставок: {exc}")
        return []


def save_ai_learning(
    rule_type: str,
    rule_text: str,
    confidence: float,
    source: str,
) -> Optional[int]:
    """Сохранить выученное правило AI-фильтра."""
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO ai_learnings (ts, rule_type, rule_text, confidence, source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_now_iso(), str(rule_type), str(rule_text), float(confidence), str(source)),
            )
            conn.commit()
            return cur.lastrowid
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Не удалось сохранить AI-правило: {exc}")
        return None


def get_ai_learnings(limit: int = 20) -> list[dict[str, Any]]:
    """Получить последние выученные правила AI-фильтра."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, rule_type, rule_text, confidence, source
                FROM ai_learnings
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения AI-правил: {exc}")
        return []


def get_bookmaker_stats(bookmaker: str) -> dict[str, Any]:
    """Получить статистику букмекера: total_bets, cancelled_pct, avg_pnl, trap_rate.

    trap_rate - доля проигранных ставок типа surebet (ловушки букмекера).
    """
    stats: dict[str, Any] = {
        "total_bets": 0,
        "cancelled_pct": 0.0,
        "avg_pnl": 0.0,
        "trap_rate": 0.0,
    }
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN result='VOID' THEN 1 ELSE 0 END) AS cancelled,
                    COALESCE(AVG(pnl), 0.0) AS avg_pnl
                FROM bets
                WHERE bookmaker = ?
                """,
                (str(bookmaker),),
            ).fetchone()
            if row and row["total"]:
                total = int(row["total"])
                stats["total_bets"] = total
                stats["cancelled_pct"] = round(
                    int(row["cancelled"] or 0) / total * 100.0, 2
                )
                stats["avg_pnl"] = round(float(row["avg_pnl"] or 0.0), 4)

            # trap_rate: LOST bets where arb_type is surebet
            trap_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS surebet_total,
                    SUM(CASE WHEN b.result='LOST' THEN 1 ELSE 0 END) AS lost
                FROM bets b
                JOIN arbs a ON a.id = b.arb_id
                WHERE b.bookmaker = ? AND a.arb_type LIKE 'surebet%'
                """,
                (str(bookmaker),),
            ).fetchone()
            if trap_row and trap_row["surebet_total"]:
                surebet_total = int(trap_row["surebet_total"])
                if surebet_total > 0:
                    stats["trap_rate"] = round(
                        int(trap_row["lost"] or 0) / surebet_total * 100.0, 2
                    )
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения статистики букмекера: {exc}")
    return stats


def get_pending_bets_for_settlement() -> list[dict[str, Any]]:
    """Получить PENDING/SIMULATED ставки старше 3 часов для расчёта."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT b.id, b.arb_id, b.ts, b.bookmaker, b.event,
                       b.outcome, b.stake, b.odds, b.result, b.pnl,
                       a.arb_type, a.commence_time, a.sport
                FROM bets b
                LEFT JOIN arbs a ON a.id = b.arb_id
                WHERE b.result IN ('PENDING', 'SIMULATED')
                  AND b.ts <= datetime('now', '-3 hours')
                ORDER BY b.id ASC
                """
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения ставок для settlement: {exc}")
        return []


def get_arb_by_id(arb_id: int) -> Optional[dict[str, Any]]:
    """Получить запись арбитража по id."""
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT id, ts, sport, event, arb_type, bookmakers_json,
                       odds_json, profit_pct, edge_pct, ai_score, status
                FROM arbs
                WHERE id = ?
                """,
                (int(arb_id),),
            ).fetchone()
            if row:
                data = dict(row)
                try:
                    data["bookmakers"] = json.loads(data.pop("bookmakers_json") or "[]")
                except (json.JSONDecodeError, TypeError):
                    data["bookmakers"] = []
                try:
                    data["odds"] = json.loads(data.pop("odds_json") or "{}")
                except (json.JSONDecodeError, TypeError):
                    data["odds"] = {}
                return data
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения арбитража #{arb_id}: {exc}")
    return None


def update_daily_pnl(date: str, staked: float, won: float, pnl: float, roi: float) -> None:
    """Обновить или вставить запись daily_pnl за указанную дату."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO daily_pnl (date, total_staked, total_won, pnl, roi_pct)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    total_staked = excluded.total_staked,
                    total_won = excluded.total_won,
                    pnl = excluded.pnl,
                    roi_pct = excluded.roi_pct
                """,
                (str(date), float(staked), float(won), float(pnl), float(roi)),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка обновления daily_pnl: {exc}")
