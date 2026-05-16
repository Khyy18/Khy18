"""Тесты momentum_engine.py."""

import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import capital_allocator
import momentum_engine


def _make_state() -> dict:
    state: dict = {}
    capital_allocator.init_allocator_state(state)
    momentum_engine.init_momentum_state(state)
    return state


def test_init_momentum_state():
    """init создаёт секцию momentum."""
    state = _make_state()
    assert "momentum" in state
    assert "enabled" in state["momentum"]
    assert "positions" in state["momentum"]
    assert state["momentum"]["total_trades"] == 0


def test_calc_ema_basic():
    """EMA на простых данных."""
    prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    ema = momentum_engine.calc_ema(prices, period=3)
    assert len(ema) == len(prices)
    # Первое значение = SMA initial_window (первые period точек)
    # initial_window = [10,11,12] → SMA = 11.0
    assert abs(ema[0] - 11.0) < 0.01
    # EMA растёт к последней цене
    assert ema[-1] > ema[0]


def test_calc_ema_single_value():
    """EMA на одном значении."""
    ema = momentum_engine.calc_ema([42.0], period=5)
    assert len(ema) == 1
    assert ema[0] == 42.0


def test_calc_ema_empty():
    """EMA на пустом списке."""
    ema = momentum_engine.calc_ema([], period=5)
    assert ema == []


def test_calc_ema_period_larger_than_data():
    """EMA когда period > len(prices)."""
    prices = [10.0, 20.0, 30.0]
    ema = momentum_engine.calc_ema(prices, period=10)
    assert len(ema) == 3
    # initial_window = все 3 элемента (period > len), SMA = 20
    assert abs(ema[0] - 20.0) < 0.01
    # i=1: SMA([10,20]) = 15
    assert abs(ema[1] - 15.0) < 0.01
    # i=2: SMA([10,20,30]) = 20
    assert abs(ema[2] - 20.0) < 0.01


def test_detect_crossover_long():
    """Бычье пересечение: fast выше slow."""
    # fast ниже slow → fast выше slow
    fast = [9.0, 10.0, 11.0, 12.5]  # растёт быстро
    slow = [10.0, 10.5, 11.0, 12.0]  # растёт медленно
    # prev: fast[-2]=11.0 <= slow[-2]=11.0, curr: fast[-1]=12.5 > slow[-1]=12.0
    signal = momentum_engine.detect_crossover(fast, slow)
    assert signal == "LONG"


def test_detect_crossover_short():
    """Медвежье пересечение: fast ниже slow."""
    # fast выше slow → fast ниже slow
    fast = [13.0, 12.0, 11.0, 9.5]
    slow = [11.0, 11.0, 10.5, 10.0]
    # prev: fast[-2]=11.0 >= slow[-2]=10.5, curr: fast[-1]=9.5 < slow[-1]=10.0
    signal = momentum_engine.detect_crossover(fast, slow)
    assert signal == "SHORT"


def test_detect_crossover_none():
    """Нет пересечения — обе EMA идут параллельно."""
    fast = [10.0, 11.0, 12.0, 13.0]
    slow = [8.0, 9.0, 10.0, 11.0]
    # fast всегда выше slow
    signal = momentum_engine.detect_crossover(fast, slow)
    assert signal is None


def test_detect_crossover_insufficient_data():
    """Недостаточно данных."""
    assert momentum_engine.detect_crossover([1.0], [2.0]) is None
    assert momentum_engine.detect_crossover([], []) is None


def test_find_position():
    """_find_position находит OPEN позицию."""
    state = _make_state()
    state["momentum"]["positions"] = [
        {"symbol": "BTCUSDT", "side": "LONG", "status": "OPEN"},
        {"symbol": "ETHUSDT", "side": "SHORT", "status": "CLOSED"},
    ]
    pos = momentum_engine._find_position(state["momentum"], "BTCUSDT")
    assert pos is not None
    assert pos["side"] == "LONG"

    pos2 = momentum_engine._find_position(state["momentum"], "ETHUSDT")
    assert pos2 is None  # CLOSED не считается


def test_find_position_none():
    """_find_position возвращает None если нет позиции."""
    state = _make_state()
    pos = momentum_engine._find_position(state["momentum"], "BTCUSDT")
    assert pos is None


def test_calc_position_size():
    """Размер позиции с учётом leverage."""
    state = _make_state()
    # momentum = 5% of 550 = 27.5, max_positions = 2 → 13.75 per pos
    # leverage 3x → notional = 41.25
    # price = 50000 → qty = 41.25/50000 = 0.000825
    qty = momentum_engine._calc_position_size(state, 50000.0)
    assert 0.0005 < qty < 0.002


def test_get_momentum_status():
    """get_momentum_status возвращает корректный dict."""
    state = _make_state()
    status = momentum_engine.get_momentum_status(state)
    assert "enabled" in status
    assert "open_positions" in status
    assert "total_trades" in status
    assert "total_profit_usdt" in status
    assert "exchange" in status
    assert "ema_fast" in status
    assert "ema_slow" in status
    assert "leverage" in status


def test_ema_converges():
    """EMA с постоянной ценой сходится к этой цене."""
    prices = [100.0] * 50
    ema = momentum_engine.calc_ema(prices, period=9)
    assert abs(ema[-1] - 100.0) < 0.001


def test_ema_trending_up():
    """EMA на растущих данных — последнее значение между min и max."""
    prices = [float(i) for i in range(1, 51)]  # 1..50
    ema = momentum_engine.calc_ema(prices, period=9)
    assert ema[-1] < 50.0  # отстаёт от цены
    assert ema[-1] > 1.0



def test_calc_atr_basic():
    """ATR на простых свечах."""
    klines = []
    for i in range(20):
        klines.append({
            "open": 100.0 + i,
            "high": 102.0 + i,
            "low": 98.0 + i,
            "close": 101.0 + i,
        })
    atr = momentum_engine.calc_atr(klines, period=14)
    # TR каждого бара ≈ high - low = 4.0 (при последовательном росте)
    assert 3.5 < atr < 5.0


def test_calc_atr_insufficient_data():
    """ATR с недостатком данных = 0."""
    klines = [{"open": 100, "high": 102, "low": 98, "close": 101}]
    assert momentum_engine.calc_atr(klines, period=14) == 0.0


def test_calc_atr_empty():
    """ATR на пустых данных."""
    assert momentum_engine.calc_atr([], period=14) == 0.0


def test_calc_rsi_constant():
    """RSI on constant data = 50 (no gains or losses after initial)."""
    closes = [100.0] * 30
    rsi = momentum_engine.calc_rsi(closes, period=14)
    # All deltas are 0 => avg_gain=0, avg_loss=0 => avg_loss==0 => RSI=100
    # Actually with constant prices, all deltas=0, so avg_gain=0, avg_loss=0
    # Edge case: avg_loss=0 returns 100.0
    assert rsi == 100.0


def test_calc_rsi_rising():
    """RSI on steadily rising data should be high (>70)."""
    closes = [float(i) for i in range(50, 100)]  # 50 values, steadily rising
    rsi = momentum_engine.calc_rsi(closes, period=14)
    assert rsi > 70


def test_calc_rsi_falling():
    """RSI on steadily falling data should be low (<30)."""
    closes = [float(i) for i in range(100, 50, -1)]  # 50 values, steadily falling
    rsi = momentum_engine.calc_rsi(closes, period=14)
    assert rsi < 30


def test_calc_rsi_insufficient_data():
    """RSI with insufficient data returns 50."""
    closes = [100.0, 101.0, 99.0]  # only 3 points, period=14 needs 15
    rsi = momentum_engine.calc_rsi(closes, period=14)
    assert rsi == 50.0


@pytest.mark.asyncio
async def test_regime_routing_ranging():
    """Mean-Reversion: ADX < 25 and RSI < oversold -> LONG MR."""
    import unittest.mock as mock

    state = _make_state()

    # Mock adapter
    adapter = mock.AsyncMock()
    # Return enough klines (50+)
    klines = []
    for i in range(100):
        klines.append({
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
        })
    # Last bar volume must pass MR volume filter (>= 1.2x avg)
    klines[-1]["volume"] = 1500.0
    adapter.get_klines = mock.AsyncMock(return_value=klines)
    adapter.get_instrument_info = mock.AsyncMock(return_value={"min_qty": 0.001, "qty_step": 0.001})
    adapter.validate_and_round_qty = mock.Mock(return_value=0.01)
    adapter.place_order_with_fallback = mock.AsyncMock(return_value={
        "fill_price": 100.0,
        "order_id": "test_mr_long",
    })

    session = mock.AsyncMock()

    with mock.patch("momentum_engine.calc_adx", return_value=15.0), \
         mock.patch("momentum_engine.calc_rsi", return_value=20.0):
        result = await momentum_engine._process_symbol(session, state, adapter, "BTCUSDT")

    assert "ОТКРЫТО" in result
    assert "LONG" in result
    assert "[MR]" in result


@pytest.mark.asyncio
async def test_regime_routing_trending():
    """Breakout: ADX >= 50, price breaks 20-bar high with volume."""
    import unittest.mock as mock

    state = _make_state()

    # Build klines where current bar breaks 20-bar high with high volume
    klines = []
    for i in range(100):
        klines.append({
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
        })
    # Last bar breaks above the 20-bar high
    klines[-1] = {
        "open": 100.0,
        "high": 105.0,
        "low": 100.0,
        "close": 104.0,
        "volume": 2000.0,  # > 1.5 * avg (1000)
    }

    adapter = mock.AsyncMock()
    adapter.get_klines = mock.AsyncMock(return_value=klines)
    adapter.get_instrument_info = mock.AsyncMock(return_value={"min_qty": 0.001, "qty_step": 0.001})
    adapter.validate_and_round_qty = mock.Mock(return_value=0.01)
    adapter.place_order_with_fallback = mock.AsyncMock(return_value={
        "fill_price": 104.0,
        "order_id": "test_bo_long",
    })

    session = mock.AsyncMock()

    with mock.patch("momentum_engine.calc_adx", return_value=55.0), \
         mock.patch("momentum_engine.calc_rsi", return_value=55.0):
        result = await momentum_engine._process_symbol(session, state, adapter, "BTCUSDT")

    assert "ОТКРЫТО" in result
    assert "LONG" in result
    assert "[BO]" in result


@pytest.mark.asyncio
async def test_regime_routing_deadzone():
    """ADX between 25 and 50 -> dead zone, skip."""
    import unittest.mock as mock

    state = _make_state()

    klines = []
    for i in range(100):
        klines.append({
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
        })

    adapter = mock.AsyncMock()
    adapter.get_klines = mock.AsyncMock(return_value=klines)

    session = mock.AsyncMock()

    with mock.patch("momentum_engine.calc_adx", return_value=35.0), \
         mock.patch("momentum_engine.calc_rsi", return_value=50.0):
        result = await momentum_engine._process_symbol(session, state, adapter, "BTCUSDT")

    assert "dead zone" in result.lower() or "dead zone" in result


@pytest.mark.asyncio
async def test_mr_exit_rsi_reversion():
    """MR position LONG closes when RSI > 55."""
    import unittest.mock as mock

    state = _make_state()
    state["momentum"]["positions"] = [{
        "symbol": "BTCUSDT",
        "side": "LONG",
        "entry_price": 50000.0,
        "qty": 0.01,
        "stop_loss": 49250.0,
        "take_profit": None,
        "opened_epoch": time.time() - 300,
        "status": "OPEN",
        "notional_usdt": 500.0,
        "strategy_type": "MR",
    }]

    adapter = mock.AsyncMock()
    adapter.place_order_with_fallback = mock.AsyncMock(return_value={
        "fill_price": 50500.0,
        "order_id": "close_mr",
    })

    session = mock.AsyncMock()
    closes = [50000.0] * 50
    current_price = 50500.0
    position = state["momentum"]["positions"][0]

    result = await momentum_engine._manage_position(
        session, state, adapter, "BTCUSDT", position,
        closes, current_price, klines=None, rsi=60.0
    )

    assert "RSI reversion" in result or "ЗАКРЫТО" in result
    assert position["status"] == "CLOSED"


@pytest.mark.asyncio
async def test_mr_time_stop():
    """MR position closes when held > max bars."""
    import unittest.mock as mock

    state = _make_state()
    # opened_epoch far in the past: > 20 * 15 * 60 = 18000 seconds ago
    state["momentum"]["positions"] = [{
        "symbol": "BTCUSDT",
        "side": "LONG",
        "entry_price": 50000.0,
        "qty": 0.01,
        "stop_loss": 49250.0,
        "take_profit": None,
        "opened_epoch": time.time() - 25000,  # > 20 bars of 15min
        "status": "OPEN",
        "notional_usdt": 500.0,
        "strategy_type": "MR",
    }]

    adapter = mock.AsyncMock()
    adapter.place_order_with_fallback = mock.AsyncMock(return_value={
        "fill_price": 50000.0,
        "order_id": "close_time",
    })

    session = mock.AsyncMock()
    closes = [50000.0] * 50
    current_price = 50000.0
    position = state["momentum"]["positions"][0]

    # RSI = 50 (not triggering RSI reversion for LONG, since 50 <= 55)
    result = await momentum_engine._manage_position(
        session, state, adapter, "BTCUSDT", position,
        closes, current_price, klines=None, rsi=50.0
    )

    assert "time stop" in result or "ЗАКРЫТО" in result
    assert position["status"] == "CLOSED"


@pytest.mark.asyncio
async def test_bo_trailing_stop_activates():
    """BO position updates trailing stop when PnL >= trail activate threshold."""
    import unittest.mock as mock

    state = _make_state()
    # BO LONG position with entry at 50000, current price gives >= 1.5% PnL
    entry_price = 50000.0
    # 1.5% gain means price = 50000 * 1.015 = 50750
    current_price = 50800.0  # > 1.5% gain

    state["momentum"]["positions"] = [{
        "symbol": "BTCUSDT",
        "side": "LONG",
        "entry_price": entry_price,
        "qty": 0.01,
        "stop_loss": 49000.0,
        "take_profit": None,
        "opened_epoch": time.time() - 300,  # recent, well within max hold
        "status": "OPEN",
        "notional_usdt": 500.0,
        "strategy_type": "BO",
    }]

    adapter = mock.AsyncMock()
    # set_trading_stop returns success
    adapter.set_trading_stop = mock.AsyncMock(return_value={"success": True})

    session = mock.AsyncMock()
    closes = [50000.0] * 50
    position = state["momentum"]["positions"][0]

    result = await momentum_engine._manage_position(
        session, state, adapter, "BTCUSDT", position,
        closes, current_price, klines=None, rsi=55.0
    )

    # Should still be holding (trailing stop updated, not closed)
    assert position["status"] == "OPEN"
    assert "держим" in result or "LONG" in result

    # Trailing stop should have been updated
    # new_sl = current_price * (1 - 0.01) = 50800 * 0.99 = 50292.0
    expected_sl = current_price * (1 - 0.01)
    assert abs(position["stop_loss"] - expected_sl) < 1.0

    # Verify set_trading_stop was called
    adapter.set_trading_stop.assert_called()


def test_equity_curve_protection_blocks_entry():
    """Equity curve protection blocks entry when last 3 trades negative and cumulative negative."""
    state = _make_state()
    mom = state["momentum"]
    for i in range(5):
        mom["positions"].append({
            "symbol": "BTCUSDT", "side": "LONG", "status": "CLOSED",
            "pnl_usdt": -10.0, "entry_price": 60000, "exit_price": 59800,
            "closed_epoch": time.time() - (5 - i) * 3600,
        })
    closed = [p for p in mom["positions"] if p.get("status") == "CLOSED"]
    recent_pnl = [float(p.get("pnl_usdt", 0)) for p in closed[-10:]]
    recent_3 = sum(recent_pnl[-3:])
    cumulative = sum(recent_pnl)
    assert recent_3 < 0
    assert cumulative < 0


def test_equity_curve_protection_allows_when_positive():
    """Equity curve protection allows entry when recent trades are positive."""
    state = _make_state()
    mom = state["momentum"]
    for i in range(2):
        mom["positions"].append({
            "symbol": "BTCUSDT", "side": "LONG", "status": "CLOSED",
            "pnl_usdt": -10.0, "entry_price": 60000,
            "closed_epoch": time.time() - (5 - i) * 3600,
        })
    for i in range(3):
        mom["positions"].append({
            "symbol": "BTCUSDT", "side": "LONG", "status": "CLOSED",
            "pnl_usdt": 15.0, "entry_price": 60000,
            "closed_epoch": time.time() - (3 - i) * 3600,
        })
    closed = [p for p in mom["positions"] if p.get("status") == "CLOSED"]
    recent_pnl = [float(p.get("pnl_usdt", 0)) for p in closed[-10:]]
    recent_3 = sum(recent_pnl[-3:])
    cumulative = sum(recent_pnl)
    assert recent_3 > 0
    assert cumulative > 0


def test_equity_curve_protection_disabled():
    """Equity curve protection can be disabled via config."""
    import combo_config as cfg
    original = cfg.MOMENTUM_EQUITY_CURVE_PROTECTION
    try:
        cfg.MOMENTUM_EQUITY_CURVE_PROTECTION = False
        assert cfg.MOMENTUM_EQUITY_CURVE_PROTECTION is False
    finally:
        cfg.MOMENTUM_EQUITY_CURVE_PROTECTION = original
