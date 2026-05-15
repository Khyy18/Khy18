"""Тесты funding_history: запись snapshots, anti-spike фильтр."""

from unittest.mock import patch

import pytest


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """SQLite в tmp_path вместо рабочего trades.db."""
    db_path = tmp_path / "test_trades.db"
    import memory
    import funding_history as fh
    monkeypatch.setattr(memory, "DB_PATH", str(db_path))
    fh.init_db()
    yield fh


class _MockSnap:
    def __init__(self, exchange, symbol, rate, apr):
        self.exchange = exchange
        self.symbol = symbol
        self.funding_rate = rate
        self.apr = apr
        self.mark_price = 100.0
        self.interval_hours = 8.0


def test_record_and_read_back(tmp_db):
    fh = tmp_db
    snapshots = {
        "bybit": [_MockSnap("bybit", "BTCUSDT", 0.0001, 0.10)],
        "okx":   [_MockSnap("okx", "BTCUSDT", -0.0002, -0.20)],
    }
    n = fh.record_snapshots(snapshots)
    assert n == 2
    # Запишем ещё несколько раз — наберётся mean.
    for apr in (0.12, 0.11, 0.13):
        fh.record_snapshots({"bybit": [_MockSnap("bybit", "BTCUSDT", 0.0001, apr)]})
    mean = fh.mean_apr("bybit", "BTCUSDT", window_hours=24)
    assert mean is not None
    assert 0.09 < mean < 0.13  # среднее в районе 0.11


def test_mean_returns_none_when_too_few_points(tmp_db):
    fh = tmp_db
    snapshots = {"bybit": [_MockSnap("bybit", "BTCUSDT", 0.0001, 0.10)]}
    fh.record_snapshots(snapshots)
    assert fh.mean_apr("bybit", "BTCUSDT") is None  # 1 точка < 3


def test_is_spike_false_when_no_history(tmp_db):
    fh = tmp_db
    # Истории нет — фильтр не должен блокировать.
    assert fh.is_spike("bybit", "BTCUSDT", 0.30, "okx", -0.05) is False


def test_is_spike_true_when_current_far_above_mean(tmp_db, monkeypatch):
    fh = tmp_db
    import config
    monkeypatch.setattr(config, "FUNDING_SPIKE_RATIO", 2.0, raising=False)
    # Накопим mean ≈ 0.10 на bybit.
    for apr in (0.10, 0.11, 0.09):
        fh.record_snapshots({"bybit": [_MockSnap("bybit", "BTCUSDT", 0.0001, apr)]})
    # Накопим mean ≈ -0.05 на okx.
    for apr in (-0.05, -0.06, -0.04):
        fh.record_snapshots({"okx": [_MockSnap("okx", "BTCUSDT", -0.0001, apr)]})
    # Текущий edge = 0.30 - (-0.20) = 0.50, mean edge = 0.10 - (-0.05) = 0.15.
    # 0.50 > 2.0 * 0.15 = 0.30 → spike.
    assert fh.is_spike("bybit", "BTCUSDT", 0.30, "okx", -0.20) is True


def test_is_spike_false_when_current_close_to_mean(tmp_db):
    fh = tmp_db
    for apr in (0.10, 0.11, 0.09):
        fh.record_snapshots({"bybit": [_MockSnap("bybit", "BTCUSDT", 0.0001, apr)]})
    for apr in (-0.05, -0.06, -0.04):
        fh.record_snapshots({"okx": [_MockSnap("okx", "BTCUSDT", -0.0001, apr)]})
    # Текущий edge близок к среднему — не спайк.
    assert fh.is_spike("bybit", "BTCUSDT", 0.11, "okx", -0.06) is False


def test_disabled_when_ratio_le_one(tmp_db, monkeypatch):
    fh = tmp_db
    import config
    monkeypatch.setattr(config, "FUNDING_SPIKE_RATIO", 0.0, raising=False)
    # Даже при катастрофическом spike фильтр выключен.
    for apr in (0.05, 0.05, 0.05):
        fh.record_snapshots({"bybit": [_MockSnap("bybit", "BTCUSDT", 0.0001, apr)]})
    for apr in (-0.05, -0.05, -0.05):
        fh.record_snapshots({"okx": [_MockSnap("okx", "BTCUSDT", -0.0001, apr)]})
    assert fh.is_spike("bybit", "BTCUSDT", 5.0, "okx", -5.0) is False
