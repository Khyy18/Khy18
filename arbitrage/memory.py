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
from datetime import datetime, timedelta, timezone
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
            # Добавляем event_id если таблица уже существовала без этого столбца
            try:
                conn.execute(
                    "ALTER TABLE arbs ADD COLUMN event_id TEXT"
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bookmaker TEXT NOT NULL UNIQUE,
                    balance REAL NOT NULL DEFAULT 0,
                    last_updated TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bankroll_state (
                    id INTEGER PRIMARY KEY,
                    total_bankroll REAL NOT NULL,
                    last_updated TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    arb_id INTEGER,
                    ai_score INTEGER,
                    actual_outcome TEXT,
                    ttl_predicted_sec INTEGER,
                    ttl_actual_sec INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_ts TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bk_classifications (
                    bookmaker TEXT PRIMARY KEY,
                    risk_level TEXT NOT NULL,
                    days_to_cut INTEGER,
                    recommendation TEXT,
                    updated_ts TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS clv_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bet_id INTEGER,
                    event_id TEXT,
                    sport TEXT,
                    placement_odds REAL,
                    closing_odds REAL,
                    clv_pct REAL,
                    checked_ts TEXT,
                    created_ts TEXT,
                    outcome TEXT
                )
                """
            )
            # Добавляем outcome если таблица уже существовала без этого столбца
            try:
                conn.execute(
                    "ALTER TABLE clv_records ADD COLUMN outcome TEXT"
                )
            except sqlite3.OperationalError:
                pass  # столбец уже существует
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts_pool (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bookmaker TEXT NOT NULL,
                    account_name TEXT NOT NULL,
                    balance REAL DEFAULT 0,
                    daily_limit REAL DEFAULT 1000,
                    daily_used REAL DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    last_bet_ts TEXT,
                    cooldown_until TEXT
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
    event_id: Optional[str] = None,
) -> Optional[int]:
    """Записать найденный арбитраж. Возвращает id записи."""
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO arbs
                    (ts, sport, event, arb_type, bookmakers_json, odds_json,
                     profit_pct, edge_pct, ai_score, status, event_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    event_id,
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
        cutoff = (datetime.now(timezone.utc) - timedelta(days=int(days))).strftime("%Y-%m-%d")
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, date, total_staked, total_won, pnl, roi_pct
                FROM daily_pnl
                WHERE date >= ?
                ORDER BY date DESC
                """,
                (cutoff,),
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


def get_account_age_days(bookmaker: str) -> int:
    """Вычислить возраст аккаунта (дней с первой ставки) у букмекера."""
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT MIN(ts) AS first_bet_ts
                FROM bets
                WHERE bookmaker = ?
                """,
                (str(bookmaker),),
            ).fetchone()
            if row and row["first_bet_ts"]:
                first_ts = row["first_bet_ts"]
                try:
                    first_dt = datetime.fromisoformat(first_ts)
                    if first_dt.tzinfo is None:
                        first_dt = first_dt.replace(tzinfo=timezone.utc)
                    now = datetime.now(tz=timezone.utc)
                    delta = now - first_dt
                    return max(0, delta.days)
                except (ValueError, TypeError):
                    return 0
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка вычисления возраста аккаунта {bookmaker}: {exc}")
    return 0


def get_pending_bets_for_settlement() -> list[dict[str, Any]]:
    """Получить PENDING/SIMULATED ставки старше 3 часов для расчёта."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT b.id, b.arb_id, b.ts, b.bookmaker, b.event,
                       b.outcome, b.stake, b.odds, b.result, b.pnl,
                       a.arb_type, a.commence_time, a.sport, a.event_id
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


def get_active_bets_for_cashout() -> list[dict[str, Any]]:
    """Получить активные ставки для проверки cashout (минимум 5 минут после размещения)."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT b.id, b.arb_id, b.ts, b.bookmaker, b.event,
                       b.outcome, b.stake, b.odds, b.result, b.pnl,
                       a.arb_type, a.commence_time, a.sport, a.event_id
                FROM bets b
                LEFT JOIN arbs a ON a.id = b.arb_id
                WHERE b.result IN ('PENDING', 'SIMULATED')
                  AND b.ts <= datetime('now', '-5 minutes')
                ORDER BY b.id DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения ставок для cashout: {exc}")
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


# --- Bankroll State ---


def save_bankroll_state(total: float) -> None:
    """Сохранить текущее состояние банкролла."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO bankroll_state (id, total_bankroll, last_updated)
                VALUES (1, ?, ?)
                """,
                (float(total), _now_iso()),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка сохранения банкролла: {exc}")


def load_bankroll_state() -> Optional[float]:
    """Загрузить банкролл из БД. None если нет записи."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT total_bankroll FROM bankroll_state WHERE id = 1"
            ).fetchone()
            if row:
                return float(row["total_bankroll"])
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка загрузки банкролла: {exc}")
    return None


# --- Account Balances ---


def get_account_balance(bookmaker: str) -> float:
    """Получить баланс букмекера. 0.0 если нет записи."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT balance FROM accounts WHERE bookmaker = ?",
                (str(bookmaker),),
            ).fetchone()
            if row:
                return float(row["balance"])
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения баланса {bookmaker}: {exc}")
    return 0.0


def set_account_balance(bookmaker: str, amount: float) -> None:
    """Установить баланс букмекера (INSERT OR REPLACE)."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO accounts (bookmaker, balance, last_updated)
                VALUES (?, ?, ?)
                ON CONFLICT(bookmaker) DO UPDATE SET
                    balance = excluded.balance,
                    last_updated = excluded.last_updated
                """,
                (str(bookmaker), float(amount), _now_iso()),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка установки баланса {bookmaker}: {exc}")


def get_all_account_balances() -> list[dict[str, Any]]:
    """Получить все балансы букмекеров."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT bookmaker, balance, last_updated FROM accounts ORDER BY bookmaker"
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения балансов: {exc}")
        return []


# --- AI Feedback ---


def save_ai_feedback(
    arb_id: Optional[int],
    ai_score: int,
    actual_outcome: str,
    ttl_predicted_sec: Optional[int] = None,
    ttl_actual_sec: Optional[int] = None,
) -> None:
    """Сохранить AI feedback запись."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO ai_feedback (ts, arb_id, ai_score, actual_outcome,
                                         ttl_predicted_sec, ttl_actual_sec)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    _now_iso(),
                    arb_id,
                    int(ai_score),
                    str(actual_outcome),
                    ttl_predicted_sec,
                    ttl_actual_sec,
                ),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка сохранения AI feedback: {exc}")


def get_recent_ai_feedback(limit: int = 5) -> list[dict[str, Any]]:
    """Получить последние N записей AI feedback."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, arb_id, ai_score, actual_outcome,
                       ttl_predicted_sec, ttl_actual_sec
                FROM ai_feedback
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения AI feedback: {exc}")
        return []


# --- Bot State (auto-recovery) ---


def save_bot_state(key: str, value: str) -> None:
    """Сохранить значение состояния бота по ключу."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_state (key, value, updated_ts)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_ts = excluded.updated_ts
                """,
                (str(key), str(value), _now_iso()),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка сохранения bot_state '{key}': {exc}")


def load_bot_state(key: str) -> Optional[str]:
    """Загрузить значение состояния бота по ключу. None если нет записи."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT value FROM bot_state WHERE key = ?",
                (str(key),),
            ).fetchone()
            if row:
                return str(row["value"])
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка загрузки bot_state '{key}': {exc}")
    return None


# --- Bookmaker Classifications ---


def save_bk_classification(
    bookmaker: str,
    risk_level: str,
    days_to_cut: int,
    recommendation: str,
) -> None:
    """Сохранить или обновить классификацию букмекера."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO bk_classifications (bookmaker, risk_level, days_to_cut, recommendation, updated_ts)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(bookmaker) DO UPDATE SET
                    risk_level = excluded.risk_level,
                    days_to_cut = excluded.days_to_cut,
                    recommendation = excluded.recommendation,
                    updated_ts = excluded.updated_ts
                """,
                (str(bookmaker), str(risk_level), int(days_to_cut), str(recommendation), _now_iso()),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка сохранения классификации {bookmaker}: {exc}")


def get_bk_classification(bookmaker: str) -> Optional[dict[str, Any]]:
    """Получить классификацию букмекера. None если нет записи."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT bookmaker, risk_level, days_to_cut, recommendation, updated_ts "
                "FROM bk_classifications WHERE bookmaker = ?",
                (str(bookmaker),),
            ).fetchone()
            if row:
                return dict(row)
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения классификации {bookmaker}: {exc}")
    return None


def get_all_bk_classifications() -> list[dict[str, Any]]:
    """Получить все классификации букмекеров."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT bookmaker, risk_level, days_to_cut, recommendation, updated_ts "
                "FROM bk_classifications ORDER BY bookmaker"
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения классификаций: {exc}")
        return []


# --- CLV Records ---


def save_clv_record(
    bet_id: int,
    event_id: str,
    sport: str,
    placement_odds: float,
    outcome: str = "",
) -> Optional[int]:
    """Сохранить запись CLV при размещении ставки. Возвращает id записи."""
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO clv_records (bet_id, event_id, sport, placement_odds, created_ts, outcome)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (int(bet_id), str(event_id), str(sport), float(placement_odds), _now_iso(), str(outcome)),
            )
            conn.commit()
            return cur.lastrowid
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Не удалось сохранить CLV-запись: {exc}")
        return None


def update_clv_record(record_id: int, closing_odds: float, clv_pct: float) -> None:
    """Обновить CLV-запись после проверки закрывающей линии."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                UPDATE clv_records
                SET closing_odds = ?, clv_pct = ?, checked_ts = ?
                WHERE id = ?
                """,
                (float(closing_odds), float(clv_pct), _now_iso(), int(record_id)),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Не удалось обновить CLV-запись #{record_id}: {exc}")


def get_pending_clv_checks() -> list[dict[str, Any]]:
    """Получить CLV-записи без проверки закрывающих линий (старше 30 минут)."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, bet_id, event_id, sport, placement_odds, outcome
                FROM clv_records
                WHERE closing_odds IS NULL
                  AND created_ts <= datetime('now', '-30 minutes')
                ORDER BY id ASC
                """
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения pending CLV-записей: {exc}")
        return []


def get_clv_stats() -> dict[str, Any]:
    """Получить статистику CLV: среднее значение, кол-во положительных/отрицательных."""
    stats: dict[str, Any] = {
        "avg_clv_pct": 0.0,
        "positive_count": 0,
        "negative_count": 0,
        "total_checked": 0,
    }
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(AVG(clv_pct), 0.0) AS avg_clv,
                    SUM(CASE WHEN clv_pct > 0 THEN 1 ELSE 0 END) AS positive,
                    SUM(CASE WHEN clv_pct <= 0 THEN 1 ELSE 0 END) AS negative,
                    COUNT(*) AS total
                FROM clv_records
                WHERE closing_odds IS NOT NULL
                """
            ).fetchone()
            if row and row["total"]:
                stats["avg_clv_pct"] = round(float(row["avg_clv"] or 0.0), 2)
                stats["positive_count"] = int(row["positive"] or 0)
                stats["negative_count"] = int(row["negative"] or 0)
                stats["total_checked"] = int(row["total"] or 0)
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения CLV статистики: {exc}")
    return stats


# --- Accounts Pool ---


def add_account_to_pool(
    bookmaker: str,
    account_name: str,
    balance: float = 0.0,
    daily_limit: float = 1000.0,
) -> Optional[int]:
    """Добавить аккаунт в пул. Возвращает id записи."""
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO accounts_pool (bookmaker, account_name, balance, daily_limit)
                VALUES (?, ?, ?, ?)
                """,
                (str(bookmaker), str(account_name), float(balance), float(daily_limit)),
            )
            conn.commit()
            return cur.lastrowid
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Не удалось добавить аккаунт в пул: {exc}")
        return None


def get_pool_accounts(bookmaker: Optional[str] = None) -> list[dict[str, Any]]:
    """Получить аккаунты из пула. Фильтр по букмекеру опционален."""
    try:
        with _connect() as conn:
            if bookmaker:
                rows = conn.execute(
                    """
                    SELECT id, bookmaker, account_name, balance, daily_limit,
                           daily_used, status, last_bet_ts, cooldown_until
                    FROM accounts_pool
                    WHERE bookmaker = ?
                    ORDER BY id
                    """,
                    (str(bookmaker),),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, bookmaker, account_name, balance, daily_limit,
                           daily_used, status, last_bet_ts, cooldown_until
                    FROM accounts_pool
                    ORDER BY id
                    """
                ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка чтения пула аккаунтов: {exc}")
        return []


def update_pool_account_bet(account_id: int, stake: float) -> None:
    """Обновить аккаунт после ставки (увеличить daily_used, установить last_bet_ts)."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                UPDATE accounts_pool
                SET daily_used = daily_used + ?,
                    last_bet_ts = ?
                WHERE id = ?
                """,
                (float(stake), _now_iso(), int(account_id)),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка обновления аккаунта #{account_id}: {exc}")


def reset_daily_used_pool() -> None:
    """Сбросить daily_used для всех аккаунтов (вызывается ежедневно)."""
    try:
        with _connect() as conn:
            conn.execute("UPDATE accounts_pool SET daily_used = 0")
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[ARB_MEMORY] Ошибка сброса daily_used: {exc}")
