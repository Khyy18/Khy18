"""SQLite-бэкенд хранилища (извлечён из memory.py).

Реализует StorageProtocol. Используется по умолчанию в dev-окружении.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


class SQLiteBackend:
    """Синхронный SQLite-бэкенд, совместимый с StorageProtocol."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_trades_closed_ts(self, conn: sqlite3.Connection) -> None:
        """Идемпотентно добавить колонку closed_ts в таблицу trades."""
        try:
            rows = conn.execute("PRAGMA table_info('trades')").fetchall()
            cols = {r[1] for r in rows}
            if "closed_ts" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN closed_ts TEXT")
        except sqlite3.Error as exc:
            print(f"[MEMORY] Не удалось добавить колонку closed_ts: {exc}")

    def init_db(self) -> None:
        """Создать таблицы и применить лёгкие миграции. Идемпотентно."""
        try:
            with self._connect() as conn:
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
                        outcome TEXT NOT NULL DEFAULT 'OPEN',
                        closed_ts TEXT
                    )
                    """
                )
                self._ensure_trades_closed_ts(conn)
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
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rejected_checks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        filter TEXT NOT NULL,
                        detail TEXT,
                        indicators_json TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS equity_curve (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts TEXT NOT NULL,
                        equity REAL NOT NULL,
                        hwm REAL NOT NULL,
                        drawdown REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS kv_store (
                        k TEXT PRIMARY KEY,
                        v TEXT NOT NULL,
                        updated_ts TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
            print(f"[MEMORY] База данных trades.db инициализирована: {self._db_path}")
        except sqlite3.Error as exc:
            print(f"[MEMORY] Ошибка инициализации БД: {exc}")

    def record_trade(
        self,
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
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO trades
                        (ts, symbol, side, entry, qty, ema, rsi, atr, ai_reason,
                         outcome, closed_ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        None,
                    ),
                )
                conn.commit()
                return cur.lastrowid
        except sqlite3.Error as exc:
            print(f"[MEMORY] Не удалось записать сделку: {exc}")
            return None

    def update_trade_outcome(
        self,
        trade_id: int,
        exit_price: float,
        pnl: float,
        outcome: str,
    ) -> None:
        """Обновить результат сделки (WIN/LOSS/OPEN). Ставит closed_ts = сейчас."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE trades
                    SET exit = ?, pnl = ?, outcome = ?, closed_ts = ?
                    WHERE id = ?
                    """,
                    (
                        float(exit_price),
                        float(pnl),
                        outcome,
                        _now_iso(),
                        int(trade_id),
                    ),
                )
                conn.commit()
        except sqlite3.Error as exc:
            print(f"[MEMORY] Не удалось обновить сделку #{trade_id}: {exc}")

    def record_rejection(
        self,
        reason: str,
        confidence: int,
        ctx: dict[str, Any],
    ) -> None:
        """Сохранить отклонённый сигнал (старая v1-таблица)."""
        try:
            with self._connect() as conn:
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

    def record_rejected_check(
        self,
        symbol: str,
        filter: str,
        detail: str,
        indicators: Optional[dict[str, Any]] = None,
    ) -> None:
        """v2: запись детерминированного отклонения."""
        try:
            ind_json = json.dumps(indicators or {}, ensure_ascii=False)
        except (TypeError, ValueError):
            ind_json = "{}"
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO rejected_checks
                        (ts, symbol, filter, detail, indicators_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        _now_iso(),
                        str(symbol or "-"),
                        str(filter or "-"),
                        str(detail or ""),
                        ind_json,
                    ),
                )
                conn.commit()
        except sqlite3.Error as exc:
            print(f"[MEMORY] Не удалось записать отклонение проверки: {exc}")

    def get_recent_errors(self, limit: int = 5) -> list[dict[str, Any]]:
        """Последние limit убыточных сделок (outcome='LOSS')."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, ts, symbol, side, entry, exit, qty, pnl, ema, rsi,
                           atr, ai_reason, outcome, closed_ts
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

    def get_last_rejection(self) -> Optional[dict[str, Any]]:
        """Последний отклонённый ИИ сигнал из старой таблицы rejected_signals."""
        try:
            with self._connect() as conn:
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

    def get_recent_rejected_checks(self, limit: int = 20) -> list[dict[str, Any]]:
        """Кольцевой буфер последних детерминированных отклонений v2."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, ts, symbol, filter, detail, indicators_json
                    FROM rejected_checks
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
                out: list[dict[str, Any]] = []
                for r in rows:
                    data = dict(r)
                    try:
                        data["indicators"] = json.loads(
                            data.pop("indicators_json") or "{}"
                        )
                    except json.JSONDecodeError:
                        data["indicators"] = {}
                    out.append(data)
                return out
        except sqlite3.Error as exc:
            print(f"[MEMORY] Ошибка чтения rejected_checks: {exc}")
            return []

    def get_last_rejected_check(self) -> Optional[dict[str, Any]]:
        """Последнее детерминированное отклонение v2."""
        rows = self.get_recent_rejected_checks(limit=1)
        return rows[0] if rows else None

    def get_open_trades(self) -> list[dict[str, Any]]:
        """Список сделок со статусом OPEN."""
        try:
            with self._connect() as conn:
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

    def get_stats(self) -> dict[str, Any]:
        """Сводная статистика: count, wins, losses, winrate, pnl_sum."""
        stats = {
            "count": 0,
            "wins": 0,
            "losses": 0,
            "winrate": 0.0,
            "pnl_sum": 0.0,
        }
        try:
            with self._connect() as conn:
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

    def record_equity(self, equity: float, hwm: float, drawdown: float) -> None:
        """Записать снимок эквити, HWM и текущей просадки."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO equity_curve (ts, equity, hwm, drawdown)
                    VALUES (?, ?, ?, ?)
                    """,
                    (_now_iso(), float(equity), float(hwm), float(drawdown)),
                )
                conn.commit()
        except sqlite3.Error as exc:
            print(f"[MEMORY] Не удалось записать equity-снимок: {exc}")

    def get_equity_curve(self, days: int) -> list[dict[str, Any]]:
        """Все снимки эквити за последние days суток."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, ts, equity, hwm, drawdown
                    FROM equity_curve
                    WHERE datetime(ts) >= datetime('now', ?)
                    ORDER BY id ASC
                    """,
                    (f"-{int(days)} days",),
                ).fetchall()
                return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            print(f"[MEMORY] Ошибка чтения equity_curve: {exc}")
            return []

    def get_hwm(self) -> float:
        """Наибольший HWM за всё время (или 0.0 если пусто)."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT COALESCE(MAX(hwm), 0.0) AS v FROM equity_curve"
                ).fetchone()
                return float(row["v"] if row else 0.0)
        except sqlite3.Error as exc:
            print(f"[MEMORY] Ошибка чтения HWM: {exc}")
            return 0.0

    def get_current_drawdown(self) -> float:
        """Просадка последнего снимка (или 0.0 если пусто)."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT drawdown
                    FROM equity_curve
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()
                return float(row["drawdown"]) if row else 0.0
        except sqlite3.Error as exc:
            print(f"[MEMORY] Ошибка чтения текущей просадки: {exc}")
            return 0.0

    def get_trades_since(self, days: int) -> list[dict[str, Any]]:
        """Все сделки за последние days суток."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, ts, symbol, side, entry, exit, qty, pnl, ema, rsi,
                           atr, ai_reason, outcome, closed_ts
                    FROM trades
                    WHERE datetime(ts) >= datetime('now', ?)
                    ORDER BY id ASC
                    """,
                    (f"-{int(days)} days",),
                ).fetchall()
                return [dict(r) for r in rows]
        except sqlite3.Error as exc:
            print(f"[MEMORY] Ошибка чтения get_trades_since: {exc}")
            return []

    def get_week_pnl(self) -> float:
        """Сумма pnl по сделкам, закрытым за последние 7 суток."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT COALESCE(SUM(pnl), 0.0) AS v
                    FROM trades
                    WHERE closed_ts IS NOT NULL
                      AND datetime(closed_ts) >= datetime('now', '-7 days')
                    """
                ).fetchone()
                return float(row["v"] if row else 0.0)
        except sqlite3.Error as exc:
            print(f"[MEMORY] Ошибка расчёта недельного PnL: {exc}")
            return 0.0

    def kv_set(self, key: str, value: Any) -> None:
        """Записать произвольное JSON-сериализуемое значение в kv_store."""
        try:
            payload = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as exc:
            print(f"[MEMORY] kv_set({key!r}): не сериализуется в JSON: {exc}")
            return
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO kv_store (k, v, updated_ts) VALUES (?, ?, ?)
                    ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated_ts=excluded.updated_ts
                    """,
                    (str(key), payload, _now_iso()),
                )
                conn.commit()
        except sqlite3.Error as exc:
            print(f"[MEMORY] kv_set({key!r}): {exc}")

    def kv_get(self, key: str, default: Any = None) -> Any:
        """Прочитать значение из kv_store. На любой ошибке возвращает default."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT v FROM kv_store WHERE k = ?", (str(key),)
                ).fetchone()
                if not row:
                    return default
                return json.loads(row["v"])
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            print(f"[MEMORY] kv_get({key!r}): {exc}")
            return default
