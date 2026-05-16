"""Тесты dynamic threshold per-tier (arb_executor._get_tier_threshold).

Проверяем:
  - test_tier_a_threshold_lower — символ tier_a с edge 15% > 12% → проходит.
  - test_tier_c_threshold_higher — символ tier_c с edge 25% < 35% → НЕ проходит.
  - test_fallback_threshold — нет данных → ARB_OPEN_MIN_NET_APR=20%.
"""

from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """SQLite в tmp_path вместо рабочего trades.db."""
    db_path = tmp_path / "test_trades.db"
    import memory
    import funding_history as fh
    monkeypatch.setattr(memory, "DB_PATH", str(db_path))
    fh.init_db()
    return str(db_path)


def _seed_history(
    db_path: str,
    symbol: str,
    cv: float,
    n_ticks: int = 250,
    mean_apr: float = 0.20,
    seed: int = 7,
    tick_minutes: int = 60,
) -> int:
    """Записать n_ticks снимков для символа с заданным cv."""
    rnd = random.Random(seed)
    mean_rate = mean_apr / 1095.0
    std_rate = cv * abs(mean_rate)
    now = datetime.now(tz=timezone.utc)

    rows: list[tuple] = []
    for i in range(n_ticks):
        ts = (now - timedelta(minutes=tick_minutes * (n_ticks - 1 - i))).isoformat(
            timespec="seconds"
        )
        rate = rnd.gauss(mean_rate, std_rate)
        apr = rate * 1095.0
        rows.append(("bybit", symbol, ts, rate, apr, 30000.0, 8.0))

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO funding_snapshots "
            "(exchange, symbol, ts, rate, apr, mark_price, interval_hours) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    return len(rows)


def test_tier_a_threshold_lower(tmp_db, monkeypatch):
    """Символ tier_a (cv < 0.30, n_obs > 200) → threshold = 12%.
    Edge 15% > 12% → кандидат проходит."""
    import config
    import arb_executor

    monkeypatch.setattr(config, "ARB_OPEN_MIN_NET_APR", 0.20, raising=False)
    monkeypatch.setattr(config, "ARB_OPEN_MIN_NET_APR_TIER_A", 0.12, raising=False)
    monkeypatch.setattr(config, "ARB_OPEN_MIN_NET_APR_TIER_B", 0.20, raising=False)
    monkeypatch.setattr(config, "ARB_OPEN_MIN_NET_APR_TIER_C", 0.35, raising=False)

    _seed_history(tmp_db, "BTCUSDT", cv=0.15, n_ticks=250, seed=101)

    threshold = arb_executor._get_tier_threshold("BTCUSDT")
    assert threshold == 0.12, f"tier_a threshold ожидался 0.12, got {threshold}"
    # Edge 15% > threshold 12% → проходит.
    assert 0.15 > threshold


def test_tier_c_threshold_higher(tmp_db, monkeypatch):
    """Символ tier_c (cv >= 0.60) → threshold = 35%.
    Edge 25% < 35% → НЕ проходит."""
    import config
    import arb_executor

    monkeypatch.setattr(config, "ARB_OPEN_MIN_NET_APR", 0.20, raising=False)
    monkeypatch.setattr(config, "ARB_OPEN_MIN_NET_APR_TIER_A", 0.12, raising=False)
    monkeypatch.setattr(config, "ARB_OPEN_MIN_NET_APR_TIER_B", 0.20, raising=False)
    monkeypatch.setattr(config, "ARB_OPEN_MIN_NET_APR_TIER_C", 0.35, raising=False)

    _seed_history(tmp_db, "WIFUSDT", cv=0.80, n_ticks=250, seed=202)

    threshold = arb_executor._get_tier_threshold("WIFUSDT")
    assert threshold == 0.35, f"tier_c threshold ожидался 0.35, got {threshold}"
    # Edge 25% < threshold 35% → НЕ проходит.
    assert 0.25 < threshold


def test_fallback_threshold(tmp_db, monkeypatch):
    """Нет данных → ARB_OPEN_MIN_NET_APR=20% (fallback)."""
    import config
    import arb_executor

    monkeypatch.setattr(config, "ARB_OPEN_MIN_NET_APR", 0.20, raising=False)
    monkeypatch.setattr(config, "ARB_OPEN_MIN_NET_APR_TIER_A", 0.12, raising=False)
    monkeypatch.setattr(config, "ARB_OPEN_MIN_NET_APR_TIER_B", 0.20, raising=False)
    monkeypatch.setattr(config, "ARB_OPEN_MIN_NET_APR_TIER_C", 0.35, raising=False)

    threshold = arb_executor._get_tier_threshold("UNKNOWNUSDT")
    assert threshold == 0.20, f"fallback threshold ожидался 0.20, got {threshold}"
