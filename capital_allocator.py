"""Аллокатор капитала между стратегиями.

Отвечает за:
  - Распределение общего equity по стратегиям (funding/grid).
  - Пересчёт при изменении аллокаций через Telegram.
  - Учёт PnL каждой стратегии отдельно и совокупно.
  - Вычисление drawdown для глобального kill-switch.
"""

from __future__ import annotations

from typing import Any

import combo_config as cfg


# ─── Инициализация state ──────────────────────────────────────────────

def init_allocator_state(state: dict[str, Any]) -> None:
    """Инициализировать секцию аллокатора в state["global"].

    Вызывается один раз при старте. Если секция уже есть -- не трогаем
    (перезапуск не сбрасывает PnL).
    """
    g = state.setdefault("global", {})

    # Общий капитал
    if "total_capital" not in g:
        g["total_capital"] = cfg.TOTAL_CAPITAL_USDT

    # Аллокации (доли)
    alloc = g.setdefault("capital_allocation", {})
    alloc.setdefault("funding", cfg.ALLOC_FUNDING_PCT)
    alloc.setdefault("grid", cfg.ALLOC_GRID_PCT)

    # PnL по стратегиям (накопительный)
    pnl = g.setdefault("strategy_pnl", {})
    pnl.setdefault("funding", 0.0)
    pnl.setdefault("grid", 0.0)

    # High-water mark для drawdown
    if "hwm_equity" not in g:
        g["hwm_equity"] = cfg.TOTAL_CAPITAL_USDT

    # Глобальный kill-switch
    g.setdefault("global_kill_active", False)
    g.setdefault("global_kill_reason", "")


# ─── Расчёты ──────────────────────────────────────────────────────────

def get_strategy_capital(state: dict[str, Any], strategy: str) -> float:
    """Сколько USDT выделено стратегии (с учётом текущего equity).

    Использует get_current_equity() (capital + PnL), а не константу
    total_capital. Так при росте/падении equity стратегии масштабируются.

    strategy: "funding" | "grid"
    """
    equity = get_current_equity(state)
    g = state.get("global", {})
    alloc = g.get("capital_allocation", {})
    pct = float(alloc.get(strategy, 0.0))
    return equity * pct


def get_current_equity(state: dict[str, Any]) -> float:
    """Текущий equity = начальный капитал + сумма PnL всех стратегий."""
    g = state.get("global", {})
    total = float(g.get("total_capital", cfg.TOTAL_CAPITAL_USDT))
    pnl = g.get("strategy_pnl", {})
    total_pnl = sum(float(v) for v in pnl.values())
    return total + total_pnl


def get_total_pnl(state: dict[str, Any]) -> float:
    """Суммарный PnL всех стратегий."""
    g = state.get("global", {})
    pnl = g.get("strategy_pnl", {})
    return sum(float(v) for v in pnl.values())


def get_drawdown_pct(state: dict[str, Any]) -> float:
    """Текущий drawdown от HWM (0.0 .. 1.0).

    0.0 = нет просадки, 0.15 = 15% просадка от пика.
    """
    g = state.get("global", {})
    hwm = float(g.get("hwm_equity", cfg.TOTAL_CAPITAL_USDT))
    if hwm <= 0:
        return 0.0
    equity = get_current_equity(state)
    dd = (hwm - equity) / hwm
    return max(0.0, dd)


def update_hwm(state: dict[str, Any]) -> None:
    """Обновить HWM если текущий equity выше."""
    g = state.get("global", {})
    equity = get_current_equity(state)
    hwm = float(g.get("hwm_equity", 0.0))
    if equity > hwm:
        g["hwm_equity"] = equity


def record_pnl(state: dict[str, Any], strategy: str, amount: float) -> None:
    """Записать PnL для стратегии (инкрементально).

    strategy: "funding" | "grid"
    amount: может быть отрицательным (убыток).
    """
    g = state.setdefault("global", {})
    pnl = g.setdefault("strategy_pnl", {})
    current = float(pnl.get(strategy, 0.0))
    pnl[strategy] = current + amount
    # Обновляем HWM после каждого положительного PnL
    if amount > 0:
        update_hwm(state)


def set_allocation(
    state: dict[str, Any],
    funding: float,
    grid: float,
) -> str | None:
    """Изменить аллокации. Возвращает None при успехе, строку ошибки иначе."""
    total = funding + grid
    if total > 1.01:
        return f"Сумма долей ({total:.2f}) > 1.0"
    if any(x < 0 for x in (funding, grid)):
        return "Доли не могут быть отрицательными"
    g = state.setdefault("global", {})
    alloc = g.setdefault("capital_allocation", {})
    alloc["funding"] = funding
    alloc["grid"] = grid
    return None


def get_allocation_summary(state: dict[str, Any]) -> dict[str, Any]:
    """Сводка аллокации для UI."""
    g = state.get("global", {})
    total = float(g.get("total_capital", cfg.TOTAL_CAPITAL_USDT))
    alloc = g.get("capital_allocation", {})
    pnl = g.get("strategy_pnl", {})
    equity = get_current_equity(state)
    dd = get_drawdown_pct(state)

    return {
        "total_capital": total,
        "current_equity": equity,
        "drawdown_pct": dd,
        "hwm": float(g.get("hwm_equity", 0.0)),
        "strategies": {
            name: {
                "alloc_pct": float(alloc.get(name, 0.0)),
                "alloc_usdt": equity * float(alloc.get(name, 0.0)),
                "pnl": float(pnl.get(name, 0.0)),
            }
            for name in ("funding", "grid")
        },
    }
