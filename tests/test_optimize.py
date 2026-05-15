"""Тесты оптимизатора momentum-стратегии (optimize.py).

Проверяем:
  - _random_params() генерирует валидные параметры с правильными диапазонами;
  - _mutate_params() сохраняет структуру и инвариант ema_fast < ema_slow;
  - _score_result() корректно считает Calmar-like score;
  - _params_to_kwargs() правильно маппит параметры для backtest;
  - _run_optimization() возвращает 4-tuple с лучшим результатом.
"""

from __future__ import annotations

import optimize
from optimize import (
    PARAM_SPACE,
    _mutate_params,
    _params_to_kwargs,
    _random_params,
    _run_optimization,
    _score_result,
)


def test_random_params_valid_ranges():
    """_random_params() возвращает dict со всеми 7 ключами PARAM_SPACE, ema_fast < ema_slow."""
    params = _random_params()

    # Все ключи присутствуют
    for key in PARAM_SPACE:
        assert key in params, f"Ключ {key} отсутствует в params"

    # ema_fast < ema_slow
    assert params["ema_fast"] < params["ema_slow"]

    # Числовые диапазоны
    assert isinstance(params["ema_fast"], int)
    assert isinstance(params["ema_slow"], int)
    assert params["stop_loss_pct"] >= 0.01
    assert params["stop_loss_pct"] <= 0.04
    assert params["take_profit_pct"] >= 0.02
    assert params["take_profit_pct"] <= 0.08
    assert params["min_atr_pct"] >= 0.003
    assert params["min_atr_pct"] <= 0.01
    assert params["trail_activate_pct"] >= 0.01
    assert params["trail_activate_pct"] <= 0.04
    assert params["trail_distance_pct"] >= 0.005
    assert params["trail_distance_pct"] <= 0.02


def test_mutate_params_preserves_structure():
    """_mutate_params() сохраняет все ключи и инвариант ema_fast < ema_slow."""
    base_params = {
        "ema_fast": 9,
        "ema_slow": 21,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04,
        "min_atr_pct": 0.005,
        "trail_activate_pct": 0.02,
        "trail_distance_pct": 0.01,
    }

    mutated = _mutate_params(base_params)

    # Те же ключи
    assert set(mutated.keys()) == set(base_params.keys())

    # Инвариант fast < slow
    assert mutated["ema_fast"] < mutated["ema_slow"]


def test_score_result_positive_pnl():
    """_score_result() с положительным PnL и достаточным числом сделок > 0."""
    result = {"total_pnl_pct": 0.5, "max_drawdown_pct": 0.1, "trades": 20}
    score = _score_result(result)
    assert score > 0


def test_score_result_zero_drawdown():
    """_score_result() с max_drawdown_pct=0 использует fallback 0.001 и не падает."""
    result = {"total_pnl_pct": 0.5, "max_drawdown_pct": 0, "trades": 20}
    score = _score_result(result)
    # Функция использует fallback 0.001, результат должен быть > 0
    assert score > 0


def test_params_to_kwargs_mapping():
    """_params_to_kwargs() правильно маппит параметры и добавляет fee/leverage/confirmation."""
    params = {
        "ema_fast": 9,
        "ema_slow": 21,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04,
        "min_atr_pct": 0.005,
        "trail_activate_pct": 0.02,
        "trail_distance_pct": 0.01,
    }

    kwargs = _params_to_kwargs(params)

    # Прямой маппинг параметров
    assert kwargs["ema_fast"] == 9
    assert kwargs["ema_slow"] == 21
    assert kwargs["stop_loss_pct"] == 0.02
    assert kwargs["take_profit_pct"] == 0.04
    assert kwargs["min_atr_pct"] == 0.005
    assert kwargs["trail_activate_pct"] == 0.02
    assert kwargs["trail_distance_pct"] == 0.01

    # Фиксированные параметры
    assert kwargs["fee_per_side"] == 0.00055
    assert "leverage" in kwargs
    assert kwargs["confirmation_bar"] is True


def test_run_optimization_basic(monkeypatch):
    """_run_optimization() с замоканным backtest возвращает 4-tuple."""
    fake_result = {
        "trades": 10,
        "winrate": 0.6,
        "total_pnl_pct": 0.05,
        "max_drawdown_pct": 0.02,
        "equity_final": 1.05,
    }

    import backtest_momentum

    monkeypatch.setattr(backtest_momentum, "run_backtest", lambda **kwargs: fake_result)

    fake_klines = [{"open": 100, "high": 101, "low": 99, "close": 100.5}] * 300

    result = _run_optimization(fake_klines, iterations=5)

    # Возвращает 4-tuple
    assert isinstance(result, tuple)
    assert len(result) == 4

    best_score, best_params, best_result, all_results = result

    # Score должен быть > 0 (PnL положительный, сделок >= 5)
    assert best_score > 0
    assert isinstance(best_params, dict)
    assert isinstance(best_result, dict)
    assert isinstance(all_results, list)
    assert len(all_results) == 5
