"""Тесты walk-forward оптимизатора (optimize.py).

Проверяем:
  - _simulate() на синтетических данных открывает пару и даёт PnL > 0;
  - optimize() возвращает <= top результатов и фильтрует по min_trades;
  - на пустой БД optimize() возвращает [] без exception;
  - --save-best пишет файл в правильном .env-формате.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


# --- Фикстуры --------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """SQLite в tmp_path вместо рабочего trades.db.

    Подменяем memory.DB_PATH (как уже делает test_funding_history.py),
    инициализируем схему funding_snapshots через funding_history.init_db().
    """
    db_path = tmp_path / "test_trades.db"
    import memory
    import funding_history as fh
    monkeypatch.setattr(memory, "DB_PATH", str(db_path))
    fh.init_db()
    return str(db_path)


def _seed_synthetic_pair(
    db_path: str,
    symbol: str = "BTCUSDT",
    long_ex: str = "okx",
    short_ex: str = "bybit",
    long_rate: float = -0.0005,
    short_rate: float = 0.001,
    n_ticks: int = 50,
    tick_minutes: int = 60,
) -> int:
    """Записать в SQLite n_ticks снимков с фиксированным edge на одной паре.

    Используем прямой INSERT (не record_snapshots), чтобы контролировать
    timestamp каждого тика — оптимизатор смотрит окно "последних N дней".

    Edge при дефолтных параметрах (рассчитан так, чтобы за 49 часов
    funding покрыл round-trip fees ~0.42 USDT и осталось положительное PnL):
      long.rate = -0.05% за 8ч → APR ≈ -54.75%
      short.rate = +0.10% за 8ч → APR ≈ +109.5%
      edge_per_hour = (0.001 - (-0.0005))/8 = 0.0001875
      edge_apr ≈ 164.25%, net_edge_apr ≈ 153% — выше всех порогов сетки.
      За 49 часов на notional 200: funding ≈ 1.84 USDT > fees 0.42 USDT.
    """
    long_apr = long_rate * (24.0 / 8.0) * 365.0
    short_apr = short_rate * (24.0 / 8.0) * 365.0
    now = datetime.now(tz=timezone.utc)

    rows: list[tuple] = []
    for i in range(n_ticks):
        # Тики в прошлом, от старого к новому. Самый поздний — сейчас.
        ts = (now - timedelta(minutes=tick_minutes * (n_ticks - 1 - i))).isoformat(
            timespec="seconds"
        )
        rows.append((long_ex, symbol, ts, long_rate, long_apr, 30000.0, 8.0))
        rows.append((short_ex, symbol, ts, short_rate, short_apr, 30000.0, 8.0))

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

def test_simulate_with_synthetic_data(tmp_db):
    """50 ticks с +33% APR edge → пара открывается и закрывается с PnL > 0."""
    import optimize

    n_inserted = _seed_synthetic_pair(tmp_db, n_ticks=50, tick_minutes=60)
    assert n_inserted == 100

    snaps = optimize._load_snapshots(tmp_db, days=7)
    assert len(snaps) == 100

    grouped = optimize._group_by_ts(snaps)
    assert len(grouped) == 50

    # Подготавливаем тики, как делает optimize().
    ticks = []
    for ts, bucket in grouped:
        lookup, cands = optimize._build_tick(bucket, holding_days=7.0)
        ticks.append((ts, lookup, cands))

    # На каждом тике должен быть минимум один кандидат.
    assert all(len(t[2]) >= 1 for t in ticks)
    # Топ-кандидат — наша пара с net_apr > 20%.
    top = ticks[0][2][0]
    assert top.symbol == "BTCUSDT"
    assert top.net_edge_apr > 0.20

    trades = optimize._simulate(
        ticks,
        open_thr=0.20,
        close_thr=0.05,
        max_hold_h=240.0,
        notional=200.0,
    )

    assert len(trades) >= 1, "пара должна открыться хотя бы раз"
    # Edge стабильно положительный → PnL > 0 после вычета комиссий.
    assert trades[0].pnl > 0
    assert trades[0].symbol == "BTCUSDT"
    assert trades[0].funding_received > 0


def test_optimize_returns_topn(tmp_db):
    """optimize() возвращает не более top результатов."""
    import optimize

    _seed_synthetic_pair(tmp_db, n_ticks=80, tick_minutes=60)

    snaps = optimize._load_snapshots(tmp_db, days=7)
    results = optimize.optimize(snaps, notional=200.0, min_trades=1, top=5)

    assert isinstance(results, list)
    assert len(results) <= 5
    # Сортировка по sharpe_proxy в убывающем порядке.
    if len(results) >= 2:
        assert results[0].sharpe_proxy >= results[1].sharpe_proxy


def test_optimize_handles_empty_db(tmp_db):
    """Пустая funding_snapshots → optimize() возвращает [] без exception."""
    import optimize

    snaps = optimize._load_snapshots(tmp_db, days=30)
    assert snaps == []

    results = optimize.optimize(snaps, notional=200.0, min_trades=10, top=10)
    assert results == []


def test_main_handles_insufficient_data(tmp_db, capsys, monkeypatch):
    """main() с пустой БД печатает сообщение и выходит с кодом 0."""
    import optimize

    rc = optimize.main(["--days", "30", "--db", tmp_db])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Недостаточно данных" in captured.out


def test_save_best_writes_env_format(tmp_path):
    """_save_best() пишет ключи ARB_* в .env-формате."""
    import optimize

    out_path = tmp_path / "best.env"
    best = optimize._ComboResult(
        open_thr=0.18,
        close_thr=0.04,
        max_hold_h=120.0,
        n_trades=42,
        total_pnl=15.50,
        mean_pnl=0.369,
        win_rate=0.71,
        sharpe_proxy=1.234,
        max_drawdown=2.10,
    )

    optimize._save_best(str(out_path), best)
    text = out_path.read_text(encoding="utf-8")
    lines = text.strip().split("\n")

    # Должны быть три KEY=VALUE строки с правильными значениями.
    assert "ARB_OPEN_MIN_NET_APR=0.1800" in lines
    assert "ARB_CLOSE_NET_APR=0.0400" in lines
    assert "ARB_MAX_HOLD_HOURS=120" in lines
    # И заголовочные комментарии.
    assert any(line.startswith("#") for line in lines)


def test_load_snapshots_filter_by_symbols(tmp_db):
    """Фильтр --symbols должен пропускать только нужные символы."""
    import optimize

    _seed_synthetic_pair(tmp_db, symbol="BTCUSDT", n_ticks=10, tick_minutes=60)
    _seed_synthetic_pair(tmp_db, symbol="ETHUSDT", n_ticks=10, tick_minutes=60)

    only_btc = optimize._load_snapshots(tmp_db, days=7, symbols_filter={"BTCUSDT"})
    assert all(s.symbol == "BTCUSDT" for s in only_btc)
    assert len(only_btc) == 20  # 10 ticks * 2 exchanges
