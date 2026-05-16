"""Тесты multi-tier position sizing (arb_executor._get_tier_notional).

Проверяем:
  - test_tier_a_for_stable_symbol — cv 0.15, n_obs 250 → 400.
  - test_tier_b_for_medium — cv 0.45 → 200.
  - test_tier_c_for_volatile — cv 0.80 → 100.
  - test_fallback_when_no_history — нет данных → ARB_NOTIONAL_USDT.
"""

from __future__ import annotations

import random
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest


# --- Фикстуры --------------------------------------------------------

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
    """Записать n_ticks снимков для символа с заданным cv (std / |mean_rate|).

    Используем фиксированный seed для детерминизма.
    """
    rnd = random.Random(seed)
    mean_rate = mean_apr / 1095.0  # APR -> per-8h rate
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


# --- Тесты -----------------------------------------------------------

def test_tier_a_for_stable_symbol(tmp_db, monkeypatch):
    """cv=0.15 + n_obs=250 → tier_a → 400 USDT."""
    import config
    import arb_executor

    monkeypatch.setattr(config, "ARB_NOTIONAL_USDT", 200.0, raising=False)
    monkeypatch.setattr(config, "ARB_NOTIONAL_TIER_A", 400.0, raising=False)
    monkeypatch.setattr(config, "ARB_NOTIONAL_TIER_B", 200.0, raising=False)
    monkeypatch.setattr(config, "ARB_NOTIONAL_TIER_C", 100.0, raising=False)

    _seed_history(tmp_db, "BTCUSDT", cv=0.15, n_ticks=250, seed=11)

    notional = arb_executor._get_tier_notional("BTCUSDT")
    assert notional == 400.0, f"tier_a ожидался 400, got {notional}"


def test_tier_b_for_medium(tmp_db, monkeypatch):
    """cv=0.45 → tier_b → 200 USDT."""
    import config
    import arb_executor

    monkeypatch.setattr(config, "ARB_NOTIONAL_USDT", 250.0, raising=False)
    monkeypatch.setattr(config, "ARB_NOTIONAL_TIER_A", 400.0, raising=False)
    monkeypatch.setattr(config, "ARB_NOTIONAL_TIER_B", 200.0, raising=False)
    monkeypatch.setattr(config, "ARB_NOTIONAL_TIER_C", 100.0, raising=False)

    _seed_history(tmp_db, "ETHUSDT", cv=0.45, n_ticks=250, seed=22)

    notional = arb_executor._get_tier_notional("ETHUSDT")
    assert notional == 200.0, f"tier_b ожидался 200, got {notional}"


def test_tier_c_for_volatile(tmp_db, monkeypatch):
    """cv=0.80 → tier_c → 100 USDT."""
    import config
    import arb_executor

    monkeypatch.setattr(config, "ARB_NOTIONAL_USDT", 250.0, raising=False)
    monkeypatch.setattr(config, "ARB_NOTIONAL_TIER_A", 400.0, raising=False)
    monkeypatch.setattr(config, "ARB_NOTIONAL_TIER_B", 200.0, raising=False)
    monkeypatch.setattr(config, "ARB_NOTIONAL_TIER_C", 100.0, raising=False)

    _seed_history(tmp_db, "JTOUSDT", cv=0.80, n_ticks=250, seed=33)

    notional = arb_executor._get_tier_notional("JTOUSDT")
    assert notional == 100.0, f"tier_c ожидался 100, got {notional}"


def test_fallback_when_no_history(tmp_db, monkeypatch):
    """Нет данных по символу → возвращает ARB_NOTIONAL_USDT (fallback)."""
    import config
    import arb_executor

    monkeypatch.setattr(config, "ARB_NOTIONAL_USDT", 200.0, raising=False)

    notional = arb_executor._get_tier_notional("UNKNOWNUSDT")
    assert notional == 200.0, f"fallback ожидался 200, got {notional}"


def test_fallback_with_one_observation(tmp_db, monkeypatch):
    """Одна запись (n_obs < 2 для stdev) → fallback к ARB_NOTIONAL_USDT."""
    import config
    import arb_executor

    monkeypatch.setattr(config, "ARB_NOTIONAL_USDT", 250.0, raising=False)

    _seed_history(tmp_db, "DOGEUSDT", cv=0.10, n_ticks=1, seed=44)

    notional = arb_executor._get_tier_notional("DOGEUSDT")
    assert notional == 250.0, (
        f"при n_obs=1 ожидаем fallback к ARB_NOTIONAL_USDT=250, got {notional}"
    )


def test_tier_b_when_obs_below_200_but_cv_low(tmp_db, monkeypatch):
    """cv 0.15 (< 0.30), но n_obs только 100 (< 200) → НЕ tier_a, а tier_b."""
    import config
    import arb_executor

    monkeypatch.setattr(config, "ARB_NOTIONAL_USDT", 200.0, raising=False)
    monkeypatch.setattr(config, "ARB_NOTIONAL_TIER_A", 400.0, raising=False)
    monkeypatch.setattr(config, "ARB_NOTIONAL_TIER_B", 200.0, raising=False)
    monkeypatch.setattr(config, "ARB_NOTIONAL_TIER_C", 100.0, raising=False)

    _seed_history(tmp_db, "SOLUSDT", cv=0.15, n_ticks=100, seed=55)

    notional = arb_executor._get_tier_notional("SOLUSDT")
    # cv низкий (0.15 < 0.30), но n_obs=100 не >200 → tier_b.
    assert notional == 200.0, (
        f"при n_obs=100 (<200) и cv<0.3 ожидаем tier_b=200, got {notional}"
    )
