"""Оптимизатор momentum-стратегии.

Подбирает параметры EMA/stop-loss/take-profit/ATR/trail
методом random search + мутации. Использует backtest_momentum.run_backtest()
для оценки каждого набора параметров.
"""

from __future__ import annotations

import random
from typing import Any

import backtest_momentum

# Пространство параметров: ключ -> (min, max, type)
PARAM_SPACE: dict[str, tuple[float, float, str]] = {
    "ema_fast": (5, 15, "int"),
    "ema_slow": (18, 50, "int"),
    "stop_loss_pct": (0.01, 0.04, "float"),
    "take_profit_pct": (0.02, 0.08, "float"),
    "min_atr_pct": (0.003, 0.01, "float"),
    "trail_activate_pct": (0.01, 0.04, "float"),
    "trail_distance_pct": (0.005, 0.02, "float"),
}


def _random_params() -> dict[str, Any]:
    """Генерирует случайный набор параметров из PARAM_SPACE.

    Гарантирует инвариант ema_fast < ema_slow.
    """
    params: dict[str, Any] = {}
    for key, (lo, hi, typ) in PARAM_SPACE.items():
        if typ == "int":
            params[key] = random.randint(int(lo), int(hi))
        else:
            params[key] = round(random.uniform(lo, hi), 6)

    # Гарантируем ema_fast < ema_slow
    if params["ema_fast"] >= params["ema_slow"]:
        params["ema_fast"], params["ema_slow"] = (
            min(params["ema_fast"], params["ema_slow"]),
            max(params["ema_fast"], params["ema_slow"]) + 1,
        )

    return params


def _mutate_params(params: dict[str, Any]) -> dict[str, Any]:
    """Мутирует набор параметров, сохраняя структуру и инвариант ema_fast < ema_slow."""
    mutated: dict[str, Any] = {}
    for key, (lo, hi, typ) in PARAM_SPACE.items():
        val = params[key]
        if typ == "int":
            delta = random.randint(-3, 3)
            new_val = max(int(lo), min(int(hi), int(val) + delta))
            mutated[key] = new_val
        else:
            spread = (hi - lo) * 0.2
            delta = random.uniform(-spread, spread)
            new_val = max(lo, min(hi, val + delta))
            mutated[key] = round(new_val, 6)

    # Гарантируем ema_fast < ema_slow
    if mutated["ema_fast"] >= mutated["ema_slow"]:
        mutated["ema_fast"], mutated["ema_slow"] = (
            min(mutated["ema_fast"], mutated["ema_slow"]),
            max(mutated["ema_fast"], mutated["ema_slow"]) + 1,
        )

    return mutated


def _score_result(result: dict[str, Any]) -> float:
    """Считает Calmar-like score: total_pnl_pct / max_drawdown_pct.

    Если max_drawdown_pct == 0, используем fallback 0.001.
    Если trades < 5, возвращает 0 (недостаточно сделок).
    """
    trades = result.get("trades", 0)
    if trades < 5:
        return 0.0

    total_pnl = result.get("total_pnl_pct", 0.0)
    max_dd = result.get("max_drawdown_pct", 0.0)

    if max_dd == 0:
        max_dd = 0.001

    return total_pnl / max_dd


def _params_to_kwargs(params: dict[str, Any]) -> dict[str, Any]:
    """Маппит параметры оптимизатора в kwargs для backtest_momentum.run_backtest().

    Добавляет фиксированные параметры: fee_per_side, leverage, confirmation_bar.
    """
    kwargs = dict(params)
    kwargs["fee_per_side"] = 0.00055
    kwargs["leverage"] = 5
    kwargs["confirmation_bar"] = True
    return kwargs


def _run_optimization(
    klines: list[dict[str, Any]],
    iterations: int = 50,
) -> tuple[float, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Запускает random-search оптимизацию.

    Returns:
        4-tuple: (best_score, best_params, best_result, all_results)
    """
    best_score = -1.0
    best_params: dict[str, Any] = {}
    best_result: dict[str, Any] = {}
    all_results: list[dict[str, Any]] = []

    current_params = _random_params()

    for _ in range(iterations):
        kwargs = _params_to_kwargs(current_params)
        kwargs["klines"] = klines

        result = backtest_momentum.run_backtest(**kwargs)
        score = _score_result(result)

        all_results.append({
            "params": current_params.copy(),
            "result": result,
            "score": score,
        })

        if score > best_score:
            best_score = score
            best_params = current_params.copy()
            best_result = result.copy()

        # Мутируем лучший или текущий
        if random.random() < 0.7 and best_params:
            current_params = _mutate_params(best_params)
        else:
            current_params = _random_params()

    return best_score, best_params, best_result, all_results
