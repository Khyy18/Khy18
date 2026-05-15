"""Хранилище открытых funding-арбитражных пар.

Отдельная таблица arb_positions в той же trades.db (см. memory.py
DB_PATH). Один процесс - одна позиция в каждый момент времени, но в БД
можем хранить историю всех закрытых пар для отчётов.

Колонки:
  id                автоинкремент
  symbol            торговый символ (BTCUSDT)
  long_exchange     биржа, на которой LONG perp
  short_exchange    биржа, на которой SHORT perp
  qty_base          размер каждой ноги в базовой валюте (BTC, ETH, ...)
  long_entry        фактическая цена входа LONG-ноги
  short_entry       фактическая цена входа SHORT-ноги
  long_order_id     биржевой ordId LONG-ноги (для аудита)
  short_order_id    биржевой ordId SHORT-ноги
  edge_apr_open     ожидаемый net APR на момент открытия (snapshot)
  funding_received  суммарно получено funding за время удержания (USDT)
  notional_usdt     приблизительная номиналы одной ноги (qty * mark)
  status            OPEN / CLOSING / CLOSED / FAILED
  opened_ts         ISO8601 UTC
  closed_ts         ISO8601 UTC (NULL пока OPEN/CLOSING)
  long_exit         цена выхода LONG (NULL до закрытия)
  short_exit        цена выхода SHORT
  pnl_directional   (long_exit - long_entry) * qty + (short_entry - short_exit) * qty
                    в USDT, без funding
  pnl_funding       сумма funding-выплат за время жизни (положительная если
                    мы получили больше, чем заплатили)
  pnl_total         pnl_directional + pnl_funding - оценочные комиссии
  fees_estimate     2 * taker_long * notional + 2 * taker_short * notional
  reason_close      строка с причиной закрытия (edge_decay / kill_switch /
                    manual / monitor_error)

Все методы возвращают dict[str, Any] (для соответствия с текущим стилем
других модулей) или None при ошибках. БД-сбои логируются, но НЕ валят
вызывающий код - executor должен корректно упасть в IDLE при потере БД.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

import memory  # для DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(memory.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def init_arb_db() -> None:
    """Создать таблицу arb_positions, если её нет. Идемпотентно.
    Вызывается из main() сразу после memory.init_db()."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS arb_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    long_exchange TEXT NOT NULL,
                    short_exchange TEXT NOT NULL,
                    qty_base REAL NOT NULL,
                    long_entry REAL NOT NULL,
                    short_entry REAL NOT NULL,
                    long_order_id TEXT,
                    short_order_id TEXT,
                    edge_apr_open REAL,
                    funding_received REAL DEFAULT 0.0,
                    notional_usdt REAL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    opened_ts TEXT NOT NULL,
                    closed_ts TEXT,
                    long_exit REAL,
                    short_exit REAL,
                    pnl_directional REAL,
                    pnl_funding REAL,
                    pnl_total REAL,
                    fees_estimate REAL,
                    reason_close TEXT
                )
                """
            )
            conn.commit()
        print("[ARB-STORE] Таблица arb_positions готова")
    except sqlite3.Error as exc:
        print(f"[ARB-STORE] Ошибка инициализации arb_positions: {exc}")


def insert_open(
    symbol: str,
    long_exchange: str,
    short_exchange: str,
    qty_base: float,
    long_entry: float,
    short_entry: float,
    long_order_id: Optional[str],
    short_order_id: Optional[str],
    edge_apr_open: float,
    notional_usdt: float,
    fees_estimate: float,
) -> Optional[int]:
    """Записать только что открытую пару. Возвращает id для дальнейших update."""
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO arb_positions
                    (symbol, long_exchange, short_exchange, qty_base,
                     long_entry, short_entry, long_order_id, short_order_id,
                     edge_apr_open, notional_usdt, status, opened_ts,
                     fees_estimate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
                """,
                (
                    symbol,
                    long_exchange,
                    short_exchange,
                    float(qty_base),
                    float(long_entry),
                    float(short_entry),
                    long_order_id,
                    short_order_id,
                    float(edge_apr_open),
                    float(notional_usdt),
                    _now_iso(),
                    float(fees_estimate),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
    except sqlite3.Error as exc:
        print(f"[ARB-STORE] insert_open fail: {exc}")
        return None


def add_funding(arb_id: int, amount_usdt: float) -> None:
    """Прибавить funding-выплату к существующей открытой паре."""
    try:
        with _connect() as conn:
            conn.execute(
                "UPDATE arb_positions SET funding_received = "
                "COALESCE(funding_received, 0) + ? WHERE id = ?",
                (float(amount_usdt), int(arb_id)),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[ARB-STORE] add_funding({arb_id}) fail: {exc}")


def mark_closing(arb_id: int) -> None:
    """Перевести пару в статус CLOSING (executor пробует закрыть обе ноги)."""
    try:
        with _connect() as conn:
            conn.execute(
                "UPDATE arb_positions SET status = 'CLOSING' WHERE id = ?",
                (int(arb_id),),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[ARB-STORE] mark_closing({arb_id}) fail: {exc}")


def insert_closed(
    arb_id: int,
    long_exit: float,
    short_exit: float,
    pnl_directional: float,
    pnl_funding: float,
    pnl_total: float,
    reason_close: str,
) -> None:
    """Закрыть пару: записать exit-цены, PnL и причину."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                UPDATE arb_positions
                SET status = 'CLOSED',
                    closed_ts = ?,
                    long_exit = ?,
                    short_exit = ?,
                    pnl_directional = ?,
                    pnl_funding = ?,
                    pnl_total = ?,
                    reason_close = ?
                WHERE id = ?
                """,
                (
                    _now_iso(),
                    float(long_exit),
                    float(short_exit),
                    float(pnl_directional),
                    float(pnl_funding),
                    float(pnl_total),
                    str(reason_close),
                    int(arb_id),
                ),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[ARB-STORE] insert_closed({arb_id}) fail: {exc}")


def mark_failed(arb_id: int, reason: str) -> None:
    """Аварийная отметка - например, мы НЕ смогли открыть вторую ногу.
    Оператор видит это в /arb_status и решает что делать."""
    try:
        with _connect() as conn:
            conn.execute(
                "UPDATE arb_positions SET status = 'FAILED', "
                "closed_ts = ?, reason_close = ? WHERE id = ?",
                (_now_iso(), str(reason)[:500], int(arb_id)),
            )
            conn.commit()
    except sqlite3.Error as exc:
        print(f"[ARB-STORE] mark_failed({arb_id}) fail: {exc}")


def get_all_active() -> list[dict[str, Any]]:
    """Все активные позиции (OPEN или CLOSING), от новейшей к старейшей.

    Поддерживает мульти-позицию: executor может держать до ARB_MAX_POSITIONS
    одновременных пар. Возвращает пустой список если нет ни одной.
    """
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM arb_positions WHERE status IN ('OPEN','CLOSING') "
                "ORDER BY id DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[ARB-STORE] get_all_active fail: {exc}")
        return []


def get_active() -> Optional[dict[str, Any]]:
    """Первая активная позиция или None. Backward-compatible обёртка над get_all_active().

    Используйте get_all_active() для полного списка (мульти-позиция).
    """
    positions = get_all_active()
    return positions[0] if positions else None


def get_recent_closed(limit: int = 20) -> list[dict[str, Any]]:
    """Последние N закрытых пар - для команды /arb_status."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM arb_positions WHERE status IN ('CLOSED','FAILED') "
                "ORDER BY id DESC LIMIT ?",
                (max(1, min(200, int(limit))),),
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        print(f"[ARB-STORE] get_recent_closed fail: {exc}")
        return []


def get_total_stats() -> dict[str, Any]:
    """Кумулятивные метрики по закрытым парам."""
    try:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS n,
                    SUM(COALESCE(pnl_total, 0)) AS pnl_sum,
                    SUM(COALESCE(pnl_funding, 0)) AS funding_sum,
                    SUM(COALESCE(pnl_directional, 0)) AS dir_sum,
                    SUM(COALESCE(fees_estimate, 0)) AS fees_sum
                FROM arb_positions
                WHERE status = 'CLOSED'
                """
            ).fetchone()
        if not row:
            return {"n": 0, "pnl_sum": 0.0, "funding_sum": 0.0,
                    "dir_sum": 0.0, "fees_sum": 0.0}
        return {
            "n": int(row["n"] or 0),
            "pnl_sum": float(row["pnl_sum"] or 0.0),
            "funding_sum": float(row["funding_sum"] or 0.0),
            "dir_sum": float(row["dir_sum"] or 0.0),
            "fees_sum": float(row["fees_sum"] or 0.0),
        }
    except sqlite3.Error as exc:
        print(f"[ARB-STORE] get_total_stats fail: {exc}")
        return {"n": 0, "pnl_sum": 0.0, "funding_sum": 0.0,
                "dir_sum": 0.0, "fees_sum": 0.0}
