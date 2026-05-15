"""Тесты grid_engine.py."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capital_allocator
import grid_engine


def _make_state() -> dict:
    state: dict = {}
    capital_allocator.init_allocator_state(state)
    grid_engine.init_grid_state(state)
    return state


def test_init_grid_state():
    """init создаёт секцию grid."""
    state = _make_state()
    assert "grid" in state
    assert "enabled" in state["grid"]
    assert "symbols" in state["grid"]
    assert state["grid"]["total_cycles"] == 0


def test_build_grid_levels():
    """build_grid_levels создаёт правильное количество уровней."""
    levels = grid_engine.build_grid_levels(
        mid_price=50000.0,
        n_levels=5,
        step_pct=0.003,
        qty_per_level=0.001,
    )
    # 5 buy + 5 sell = 10
    assert len(levels) == 10

    buy_levels = [lv for lv in levels if lv.side == "Buy"]
    sell_levels = [lv for lv in levels if lv.side == "Sell"]
    assert len(buy_levels) == 5
    assert len(sell_levels) == 5


def test_build_grid_levels_prices():
    """Цены уровней корректны."""
    mid = 1000.0
    step = 0.01  # 1%
    levels = grid_engine.build_grid_levels(mid, n_levels=3, step_pct=step, qty_per_level=1.0)

    # Buy уровни: 990, 980, 970
    buy_levels = sorted([lv for lv in levels if lv.side == "Buy"], key=lambda l: l.price, reverse=True)
    assert abs(buy_levels[0].price - 990.0) < 0.01
    assert abs(buy_levels[1].price - 980.0) < 0.01
    assert abs(buy_levels[2].price - 970.0) < 0.01

    # Sell уровни: 1010, 1020, 1030
    sell_levels = sorted([lv for lv in levels if lv.side == "Sell"], key=lambda l: l.price)
    assert abs(sell_levels[0].price - 1010.0) < 0.01
    assert abs(sell_levels[1].price - 1020.0) < 0.01
    assert abs(sell_levels[2].price - 1030.0) < 0.01


def test_build_grid_levels_sorted():
    """Уровни отсортированы по цене."""
    levels = grid_engine.build_grid_levels(50000.0, 10, 0.003, 0.001)
    prices = [lv.price for lv in levels]
    assert prices == sorted(prices)


def test_is_grid_out_of_range_empty():
    """Пустая сетка = out of range."""
    assert grid_engine.is_grid_out_of_range(50000.0, [])


def test_is_grid_out_of_range_within():
    """Цена внутри сетки — не out of range."""
    levels = grid_engine.build_grid_levels(50000.0, 5, 0.003, 0.001)
    # Цена чуть сдвинулась
    assert not grid_engine.is_grid_out_of_range(50050.0, levels)
    assert not grid_engine.is_grid_out_of_range(49950.0, levels)


def test_is_grid_out_of_range_outside():
    """Цена далеко за пределами сетки."""
    levels = grid_engine.build_grid_levels(50000.0, 5, 0.003, 0.001)
    # Сетка покрывает ±1.5% (5 * 0.3%). С tolerance 0.5 — ещё +0.75%
    # Уходим на 5% — точно out of range
    assert grid_engine.is_grid_out_of_range(52500.0, levels)
    assert grid_engine.is_grid_out_of_range(47500.0, levels)


def test_grid_level_serialization():
    """to_dict / from_dict round-trip."""
    lv = grid_engine.GridLevel(
        price=50100.0, side="Sell", qty=0.001, order_id="abc123", filled=True
    )
    d = lv.to_dict()
    assert d["price"] == 50100.0
    assert d["side"] == "Sell"
    assert d["order_id"] == "abc123"
    assert d["filled"] is True

    restored = grid_engine.GridLevel.from_dict(d)
    assert restored.price == lv.price
    assert restored.side == lv.side
    assert restored.order_id == lv.order_id
    assert restored.filled == lv.filled


def test_calc_grid_order_size():
    """Размер ордера рассчитывается из аллокации."""
    state = _make_state()
    # grid allocation = 30% of 550 = 165
    # 2 символа, 10 уровней на символ → 165/2/10 = 8.25
    size = grid_engine._calc_grid_order_size(state, 10)
    # allocated = 165 / 2 symbols / 10 levels = 8.25
    assert size >= 5.0  # минимум
    assert size <= 20.0


def test_get_grid_status():
    """get_grid_status возвращает корректный dict."""
    state = _make_state()
    status = grid_engine.get_grid_status(state)
    assert "enabled" in status
    assert "symbols" in status
    assert "total_cycles" in status
    assert "total_profit_usdt" in status
    assert "exchange" in status
    assert "levels_per_side" in status
