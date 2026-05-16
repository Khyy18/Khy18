"""Предзаполнение funding_snapshots историческими данными.

Использует Bybit /v5/market/funding/history (публичный, без auth) для
исторических rates и Binance /fapi/v1/fundingRate.

Запуск один раз перед первым main.py:
    python3 backfill_funding.py --days 7 --exchanges bybit,binance

Это заполняет funding_history так, что anti-spike фильтр и ML-predictor
имеют данные с первого тика, а не ждут 24ч.
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

import config
import funding_history
import memory


async def _backfill_bybit(
    session: aiohttp.ClientSession,
    symbols: list[str],
    days: int,
) -> list[tuple[str, str, str, float, float, float, float]]:
    """Bybit /v5/market/funding/history — публичный endpoint, без auth.
    Возвращает list of (exchange, symbol, ts_iso, rate, apr, mark_price, interval_hours).
    """
    rows: list[tuple[str, str, str, float, float, float, float]] = []
    for sym in symbols:
        url = (
            f"https://api.bybit.com/v5/market/funding/history"
            f"?category=linear&symbol={sym}&limit=200"
        )
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
        except Exception:  # noqa: BLE001
            continue

        items: list[dict[str, Any]] = ((data.get("result") or {}).get("list") or [])
        for it in items:
            try:
                rate = float(it.get("fundingRate") or 0)
                ts_ms = int(it.get("fundingRateTimestamp") or 0)
                ts_dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                # Фильтр по дням.
                if (datetime.now(tz=timezone.utc) - ts_dt).days > days:
                    continue
                apr = rate * 3 * 365  # 3 ticks per day (8h), *365
                rows.append((
                    "bybit", sym, ts_dt.isoformat(timespec="seconds"),
                    rate, apr, 0.0, 8.0,
                ))
            except (TypeError, ValueError):
                continue
    return rows


async def _backfill_binance(
    session: aiohttp.ClientSession,
    symbols: list[str],
    days: int,
) -> list[tuple[str, str, str, float, float, float, float]]:
    """Binance /fapi/v1/fundingRate — публичный."""
    rows: list[tuple[str, str, str, float, float, float, float]] = []
    since_ms = int(
        (datetime.now(tz=timezone.utc) - timedelta(days=days)).timestamp() * 1000
    )
    for sym in symbols:
        url = (
            f"https://fapi.binance.com/fapi/v1/fundingRate"
            f"?symbol={sym}&startTime={since_ms}&limit=1000"
        )
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
        except Exception:  # noqa: BLE001
            continue

        for it in (data or []):
            try:
                rate = float(it.get("fundingRate") or 0)
                ts_ms = int(it.get("fundingTime") or 0)
                ts_dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                apr = rate * 3 * 365
                rows.append((
                    "binance", sym, ts_dt.isoformat(timespec="seconds"),
                    rate, apr, 0.0, 8.0,
                ))
            except (TypeError, ValueError):
                continue
    return rows


async def run(days: int, exchanges: list[str], symbols: list[str]) -> int:
    """Основная async-логика backfill. Возвращает 0 при успехе, 1 при ошибке."""
    funding_history.init_db()

    async with aiohttp.ClientSession() as session:
        all_rows: list[tuple[str, str, str, float, float, float, float]] = []
        if "bybit" in exchanges:
            print(f"[BACKFILL] Bybit: загрузка {len(symbols)} символов за {days} дней...")
            bybit_rows = await _backfill_bybit(session, symbols, days)
            all_rows.extend(bybit_rows)
            print(f"[BACKFILL] Bybit: получено {len(bybit_rows)} записей")

        if "binance" in exchanges:
            print(f"[BACKFILL] Binance: загрузка {len(symbols)} символов за {days} дней...")
            binance_rows = await _backfill_binance(session, symbols, days)
            all_rows.extend(binance_rows)
            print(f"[BACKFILL] Binance: получено {len(binance_rows)} записей")

        if not all_rows:
            print("[BACKFILL] Нет данных для записи.")
            return 0

        # Пишем в БД.
        try:
            with sqlite3.connect(memory.DB_PATH) as conn:
                conn.executemany(
                    "INSERT OR IGNORE INTO funding_snapshots "
                    "(exchange, symbol, ts, rate, apr, mark_price, interval_hours) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    all_rows,
                )
                conn.commit()
        except sqlite3.Error as exc:
            print(f"[BACKFILL] DB write error: {exc}")
            return 1

        print(f"[BACKFILL] Записано {len(all_rows)} исторических snapshots в БД.")
        return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Парсит аргументы и запускает async run()."""
    p = argparse.ArgumentParser(
        prog="backfill_funding.py",
        description="Предзаполнение funding_snapshots историей с бирж.",
    )
    p.add_argument(
        "--days", type=int, default=7,
        help="Сколько дней истории загрузить (default 7).",
    )
    p.add_argument(
        "--exchanges", type=str, default="bybit,binance",
        help="Биржи через запятую (default bybit,binance).",
    )
    p.add_argument(
        "--symbols", type=str, default=None,
        help="Символы через запятую (default из config.FUNDING_SCAN_SYMBOLS).",
    )
    args = p.parse_args(argv)

    exchanges: list[str] = [
        e.strip().lower() for e in args.exchanges.split(",") if e.strip()
    ]
    symbols: list[str] = (
        [s.strip() for s in args.symbols.split(",") if s.strip()]
        if args.symbols
        else list(config.FUNDING_SCAN_SYMBOLS)
    )

    return asyncio.run(run(args.days, exchanges, symbols))


if __name__ == "__main__":
    sys.exit(main())
