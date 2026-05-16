"""Тесты capital_allocator.py."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import capital_allocator


def _make_state() -> dict:
    state: dict = {}
    capital_allocator.init_allocator_state(state)
    return state


def test_init_allocator_state():
    """init создаёт все нужные ключи."""
    state = _make_state()
    g = state["global"]
    assert "total_capital" in g
    assert "capital_allocation" in g
    assert "strategy_pnl" in g
    assert "hwm_equity" in g
    assert g["capital_allocation"]["funding"] == 0.75
    assert g["capital_allocation"]["grid"] == 0.25


def test_get_strategy_capital():
    """Правильно считает долю капитала."""
    state = _make_state()
    # total_capital = 550, funding = 75%
    cap = capital_allocator.get_strategy_capital(state, "funding")
    assert abs(cap - 412.5) < 0.01

    cap_grid = capital_allocator.get_strategy_capital(state, "grid")
    assert abs(cap_grid - 137.5) < 0.01


def test_get_current_equity():
    """equity = capital + sum(pnl)."""
    state = _make_state()
    assert capital_allocator.get_current_equity(state) == 550.0

    capital_allocator.record_pnl(state, "grid", 10.0)
    assert abs(capital_allocator.get_current_equity(state) - 560.0) < 0.01


def test_record_pnl():
    """record_pnl инкрементирует и обновляет HWM."""
    state = _make_state()
    capital_allocator.record_pnl(state, "grid", 5.0)
    assert state["global"]["strategy_pnl"]["grid"] == 5.0

    capital_allocator.record_pnl(state, "grid", -2.0)
    assert abs(state["global"]["strategy_pnl"]["grid"] - 3.0) < 0.01

    # HWM должен быть 555 (после +5)
    assert state["global"]["hwm_equity"] == 555.0


def test_drawdown_calculation():
    """drawdown от HWM."""
    state = _make_state()
    # Начальный drawdown = 0
    assert capital_allocator.get_drawdown_pct(state) == 0.0

    # Поднимаем HWM
    capital_allocator.record_pnl(state, "funding", 50.0)
    capital_allocator.update_hwm(state)
    assert state["global"]["hwm_equity"] == 600.0

    # Теряем 60 (10% drawdown)
    capital_allocator.record_pnl(state, "funding", -60.0)
    dd = capital_allocator.get_drawdown_pct(state)
    # equity = 550 + 50 - 60 = 540, hwm = 600, dd = (600-540)/600 = 0.1
    assert abs(dd - 0.1) < 0.01


def test_set_allocation():
    """Изменение аллокаций."""
    state = _make_state()

    # Нормальный случай
    err = capital_allocator.set_allocation(state, 0.60, 0.40)
    assert err is None
    alloc = state["global"]["capital_allocation"]
    assert alloc["funding"] == 0.60
    assert alloc["grid"] == 0.40

    # Сумма > 1
    err = capital_allocator.set_allocation(state, 0.60, 0.50)
    assert err is not None
    assert "1.0" in err

    # Отрицательная доля
    err = capital_allocator.set_allocation(state, -0.1, 0.5)
    assert err is not None


def test_get_allocation_summary():
    """Summary содержит все нужные ключи."""
    state = _make_state()
    s = capital_allocator.get_allocation_summary(state)
    assert "total_capital" in s
    assert "current_equity" in s
    assert "drawdown_pct" in s
    assert "strategies" in s
    assert "funding" in s["strategies"]
    assert "alloc_pct" in s["strategies"]["funding"]
    assert "alloc_usdt" in s["strategies"]["funding"]
    assert "pnl" in s["strategies"]["funding"]


def test_init_idempotent():
    """Повторный init не сбрасывает PnL."""
    state = _make_state()
    capital_allocator.record_pnl(state, "grid", 100.0)

    # Повторная инициализация
    capital_allocator.init_allocator_state(state)
    assert state["global"]["strategy_pnl"]["grid"] == 100.0
