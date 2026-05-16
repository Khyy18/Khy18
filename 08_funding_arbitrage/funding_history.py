"""Funding-rate history + anti-spike фильтр.

Хранит историю снимков funding по (биржа, символ) в SQLite. На каждом
funding_scan_tick вызывается record_snapshot — каждые ~5 минут.

Anti-spike: перед открытием новой пары проверяем, не является ли
текущий APR аномальным спайком относительно среднего за окно. Если да —
скорее всего edge быстро схлопнется, входить рискованно (см. учения,
сценарий "вошли на 24% APR → через 2 часа 4% → закрылись с −$0.40").

Хранение:
  Таблица funding_snapshots(exchange, symbol, ts, rate, apr).
  Чистка: записи старше FUNDING_HISTORY_RETENTION_HOURS удаляются.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import config
import memory  # для DB_PATH


_RETENTION_HOURS = 7 * 24  # 7 дней истории — больше не нужно


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(memory.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def init_db() -> None:
    """Создать таблицу funding_snapshots, если её нет. Идемпотентно."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS funding_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    rate REAL NOT NULL,
                    apr REAL NOT NULL,
                    mark_price REAL,
                    interval_hours REAL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fund_snap_lookup "
                "ON funding_snapshots(exchange, symbol, ts)"
            )
            conn.commit()
        print("[FUND-HIST] Таблица funding_snapshots готова")
    except sqlite3.Error as exc:
        print(f"[FUND-HIST] init_db fail: {exc}")


def record_snapshots(snapshots: dict[str, list[Any]]) -> int:
    """Записать пачкой все срезы из funding-сканера. Возвращает кол-во строк."""
    rows: list[tuple] = []
    ts = _now_iso()
    for ex_name, snaps in snapshots.items():
        for s in snaps:
            try:
                rows.append((
                    ex_name,
                    str(getattr(s, "symbol", "")),
                    ts,
                    float(getattr(s, "funding_rate", 0.0) or 0.0),
                    float(getattr(s, "apr", 0.0) or 0.0),
                    float(getattr(s, "mark_price", 0.0) or 0.0),
                    float(getattr(s, "interval_hours", 8.0) or 8.0),
                ))
            except (TypeError, ValueError):
                continue
    if not rows:
        return 0
    try:
        with _connect() as conn:
            conn.executemany(
                "INSERT INTO funding_snapshots "
                "(exchange, symbol, ts, rate, apr, mark_price, interval_hours) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        return len(rows)
    except sqlite3.Error as exc:
        print(f"[FUND-HIST] record_snapshots fail: {exc}")
        return 0


def cleanup_old() -> int:
    """Удалить записи старше _RETENTION_HOURS. Вызывается раз в сутки."""
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(hours=_RETENTION_HOURS)).isoformat(
        timespec="seconds"
    )
    try:
        with _connect() as conn:
            cur = conn.execute(
                "DELETE FROM funding_snapshots WHERE ts < ?", (cutoff,)
            )
            conn.commit()
            return cur.rowcount or 0
    except sqlite3.Error as exc:
        print(f"[FUND-HIST] cleanup fail: {exc}")
        return 0


def mean_apr(
    exchange: str,
    symbol: str,
    window_hours: float = 24.0,
) -> Optional[float]:
    """Средний APR по (биржа, символ) за окно. None если данных < 3 точек."""
    cutoff = (
        datetime.now(tz=timezone.utc) - timedelta(hours=window_hours)
    ).isoformat(timespec="seconds")
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT AVG(apr) AS m, COUNT(*) AS n FROM funding_snapshots "
                "WHERE exchange = ? AND symbol = ? AND ts >= ?",
                (exchange.lower(), symbol, cutoff),
            ).fetchone()
        if not row or (row["n"] or 0) < 3:
            return None
        return float(row["m"])
    except sqlite3.Error as exc:
        print(f"[FUND-HIST] mean_apr fail: {exc}")
        return None


def get_recent_for_symbol_exchange(
    exchange: str, symbol: str, hours: float = 25,
) -> list[tuple[datetime, float, float]]:
    """Вернуть (ts, rate, apr) за последние N часов для (биржа, символ).

    Используется funding_predictor для построения фич — нужна 24h+
    история, поэтому default hours=25.
    """
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT ts, rate, apr FROM funding_snapshots "
                "WHERE exchange = ? AND symbol = ? AND ts >= ? "
                "ORDER BY ts ASC",
                (exchange.lower(), symbol, cutoff),
            ).fetchall()
    except sqlite3.Error:
        return []
    out: list[tuple[datetime, float, float]] = []
    for r in rows:
        try:
            ts = datetime.fromisoformat(str(r["ts"]))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            out.append((ts, float(r["rate"]), float(r["apr"])))
        except (TypeError, ValueError):
            continue
    return out


def is_spike(
    long_exchange: str,
    symbol: str,
    long_apr_now: float,
    short_exchange: str,
    short_apr_now: float,
) -> bool:
    """Спайк = текущий edge сильно выше среднего за окно.

    Логика: считаем mean_long и mean_short за FUNDING_HISTORY_WINDOW_HOURS.
    Если |long_now - short_now| > FUNDING_SPIKE_RATIO * |mean_long - mean_short|
    — это спайк. Скорее всего edge быстро схлопнется, входить рискованно.

    Если истории мало (<3 точек на ноге) — возвращаем False (не блокируем).
    """
    ratio = float(getattr(config, "FUNDING_SPIKE_RATIO", 2.5))
    window = float(getattr(config, "FUNDING_HISTORY_WINDOW_HOURS", 24.0) or 24.0)
    if ratio <= 1.0:
        return False  # фильтр выключен

    long_mean = mean_apr(long_exchange, symbol, window)
    short_mean = mean_apr(short_exchange, symbol, window)
    if long_mean is None or short_mean is None:
        return False  # нет данных — не блокируем

    edge_now = abs(long_apr_now - short_apr_now)
    edge_mean = abs(long_mean - short_mean)
    if edge_mean < 0.01:
        # Среднее почти ноль — текущий edge гарантированно намного выше.
        # Это либо реально новая возможность, либо спайк. Решаем
        # консервативно: если edge_now > 0.30 (30% APR) и edge_mean < 0.05 —
        # явный спайк. Иначе пропускаем.
        return edge_now > 0.30

    return edge_now > ratio * edge_mean
