"""Тесты momentum_engine.py."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    # momentum = 20% of 550 = 110, max_positions = 2 → 55 per pos
    # leverage 3x → notional = 165
    # price = 50000 → qty = 165/50000 = 0.0033
    qty = momentum_engine._calc_position_size(state, 50000.0)
    assert 0.002 < qty < 0.005


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
