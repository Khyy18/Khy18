"""Runtime state helpers для combo-бота.

Вспомогательные функции проверки рисков, spread guard, correlation guard,
performance monitoring. Используются из momentum_engine, grid_engine и
combo_main.
"""

from __future__ import annotations

import time
from typing import Any

import capital_allocator
import combo_config as cfg


# ─── Spread Guard ──────────────────────────────────────────────────────

def is_spread_too_wide(best_bid: float, best_ask: float) -> bool:
    """True если spread слишком широкий (ликвидность испарилась).

    Проверяет (ask - bid) / mid > MAX_SPREAD_PCT.
    """
    if best_bid <= 0 or best_ask <= 0:
        return True
    mid = (best_bid + best_ask) / 2
    if mid <= 0:
        return True
    spread_pct = (best_ask - best_bid) / mid
    return spread_pct > cfg.MAX_SPREAD_PCT


# ─── Grid Unrealized Loss ─────────────────────────────────────────────

def calc_grid_unrealized_loss(state: dict[str, Any], current_prices: dict[str, float]) -> float:
    """Рассчитать суммарный unrealized loss по grid (все символы).

    Unrealized loss = сумма (entry_price - current_price) * qty для filled
    buy-ордеров, у которых ещё нет matched sell.

    Возвращает отрицательное число (убыток) или 0.
    """
    grid_state = state.get("grid", {})
    total_loss = 0.0

    for symbol in cfg.GRID_SYMBOLS:
        sym_state = grid_state.get("symbols", {}).get(symbol, {})
        levels_raw = sym_state.get("levels", [])
        current_price = current_prices.get(symbol, 0.0)
        if current_price <= 0:
            continue

        for d in levels_raw:
            if not d.get("filled", False):
                continue
            # Filled buy = мы купили, но sell ещё не сработал
            # Unrealized loss = (fill_price - current_price) * qty (если цена ниже)
            fill_price = float(d.get("fill_price", 0) or d.get("price", 0))
            qty = float(d.get("qty", 0))
            if d.get("side") == "Buy" and current_price < fill_price:
                total_loss += (current_price - fill_price) * qty
            elif d.get("side") == "Sell" and current_price > fill_price:
                total_loss += (fill_price - current_price) * qty

    return total_loss


def should_force_close_grid(state: dict[str, Any], current_prices: dict[str, float]) -> bool:
    """True если unrealized loss grid превышает лимит."""
    if cfg.GRID_MAX_UNREALIZED_LOSS_PCT <= 0:
        return False
    equity = capital_allocator.get_current_equity(state)
    if equity <= 0:
        return False
    loss = calc_grid_unrealized_loss(state, current_prices)
    # loss отрицательный, порог тоже (equity * -pct)
    return loss < -(equity * cfg.GRID_MAX_UNREALIZED_LOSS_PCT)


# ─── Correlation Guard ─────────────────────────────────────────────────

def check_correlation_allows_entry(state: dict[str, Any], symbol: str, signal: str) -> bool:
    """True если correlation guard разрешает открыть позицию.

    Проверяет что в одной корреляционной группе (BTC+ETH) нет позиций
    в том же направлении.
    """
    max_same = cfg.CORRELATION_MAX_SAME_DIRECTION
    if max_same <= 0:
        return True  # выключено

    # Находим группу для символа
    group: list[str] = []
    for g in cfg.CORRELATION_GROUPS:
        if symbol in g:
            group = g
            break
    if not group:
        return True  # символ не в группе

    # Считаем открытые позиции в том же направлении в этой группе
    mom_state = state.get("momentum", {})
    positions = mom_state.get("positions", [])
    same_direction_count = 0
    for pos in positions:
        if pos.get("status") != "OPEN":
            continue
        if pos.get("symbol") in group and pos.get("side") == signal:
            same_direction_count += 1

    return same_direction_count < max_same


# ─── Performance Monitoring ────────────────────────────────────────────

def get_rolling_winrate(state: dict[str, Any], window: int = 0) -> float:
    """Рассчитать rolling winrate за последние N сделок momentum.

    Возвращает 0.0 .. 1.0. Если сделок < 5 — возвращает 0.5 (neutral).
    """
    if window <= 0:
        window = cfg.PERF_ROLLING_WINDOW

    mom_state = state.get("momentum", {})
    positions = mom_state.get("positions", [])
    closed = [p for p in positions if p.get("status") == "CLOSED"]

    if len(closed) < 5:
        return 0.5  # недостаточно данных

    # Берём последние N
    recent = closed[-window:]
    wins = sum(1 for p in recent if float(p.get("pnl_usdt", 0)) > 0)
    return wins / len(recent)


def check_performance_degradation(state: dict[str, Any]) -> str | None:
    """Проверить деградацию performance.

    Возвращает текст алерта или None если всё OK.
    """
    g = state.get("global", {})
    last_alert = float(g.get("perf_degrade_alert_epoch", 0))
    if (time.time() - last_alert) < cfg.PERF_ALERT_COOLDOWN_SEC:
        return None

    winrate = get_rolling_winrate(state)
    if winrate < cfg.PERF_MIN_WINRATE:
        g["perf_degrade_alert_epoch"] = time.time()
        return (
            f"Rolling winrate упал до {winrate*100:.0f}% "
            f"(порог {cfg.PERF_MIN_WINRATE*100:.0f}%). "
            f"Рекомендуется рекалибровка параметров."
        )
    return None
