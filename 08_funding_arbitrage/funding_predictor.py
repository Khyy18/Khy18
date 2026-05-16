"""Funding direction prediction через линейную регрессию.

Простая модель — линейная регрессия методом наименьших квадратов
на pure Python (без numpy). Цель: предсказать delta funding rate в
следующие 8 часов на основе 24-часовой trajectory.

Features (8):
  1. rate_now — текущий rate
  2. rate_lag_1h — rate 1 час назад
  3. rate_lag_4h
  4. rate_lag_8h
  5. rate_lag_12h
  6. rate_lag_24h
  7. mean_rate_24h — среднее за 24h
  8. std_rate_24h — волатильность за 24h

Target: rate_next_8h - rate_now (signed delta).

Модель — словарь {weights, bias, mse}. Сериализуется в JSON.
В runtime: predict_delta(features) → знак умножается на multiplier
для скоринга кандидата.
"""

from __future__ import annotations
import json
import statistics
from datetime import datetime, timedelta, timezone
from typing import Optional


def extract_features(history: list[tuple[datetime, float, float]]) -> Optional[list[float]]:
    """Из (ts, rate, apr) последних 24+ часов вытащить 8 фич.

    None если данных мало (<10 точек или не покрывают 24h).
    """
    if not history or len(history) < 10:
        return None

    # Сортируем по времени, берём минимум 24h.
    sorted_hist = sorted(history, key=lambda x: x[0])
    now = sorted_hist[-1][0]
    earliest = sorted_hist[0][0]
    if (now - earliest).total_seconds() < 23 * 3600:
        return None

    rates = [r[1] for r in sorted_hist]
    rate_now = rates[-1]

    def _rate_at_lag(lag_hours: float) -> float:
        """Найти rate ближайший по времени к (now - lag_hours)."""
        target_ts = now - timedelta(hours=lag_hours)
        best = sorted_hist[0]
        best_diff = abs((best[0] - target_ts).total_seconds())
        for h in sorted_hist:
            diff = abs((h[0] - target_ts).total_seconds())
            if diff < best_diff:
                best_diff = diff
                best = h
        return best[1]

    rate_lag_1h = _rate_at_lag(1)
    rate_lag_4h = _rate_at_lag(4)
    rate_lag_8h = _rate_at_lag(8)
    rate_lag_12h = _rate_at_lag(12)
    rate_lag_24h = _rate_at_lag(24)

    # 24h среднее и std.
    cutoff_24h = now - timedelta(hours=24)
    rates_24h = [r[1] for r in sorted_hist if r[0] >= cutoff_24h]
    if len(rates_24h) < 2:
        return None
    mean_rate_24h = sum(rates_24h) / len(rates_24h)
    try:
        std_rate_24h = statistics.stdev(rates_24h)
    except statistics.StatisticsError:
        std_rate_24h = 0.0

    return [
        rate_now,
        rate_lag_1h,
        rate_lag_4h,
        rate_lag_8h,
        rate_lag_12h,
        rate_lag_24h,
        mean_rate_24h,
        std_rate_24h,
    ]


def train(training_data: list[tuple[list[float], float]]) -> dict:
    """Линейная регрессия методом градиентного спуска.

    training_data: list of (features, target_delta).
    Возвращает {weights, bias, mse}.

    Реализация — gradient descent на pure Python (нормальные уравнения требуют
    инверсию матрицы — это сложнее без numpy). 1000 итераций с lr=0.01 — этого
    достаточно для convergence на маленьких dataset'ах.
    """
    if not training_data:
        return {"weights": [0.0] * 8, "bias": 0.0, "mse": 0.0}

    n_features = len(training_data[0][0])
    weights = [0.0] * n_features
    bias = 0.0
    lr = 0.01
    iterations = 1000

    for _ in range(iterations):
        grad_w = [0.0] * n_features
        grad_b = 0.0
        for x, y in training_data:
            pred = sum(w * f for w, f in zip(weights, x)) + bias
            err = pred - y
            for i in range(n_features):
                grad_w[i] += err * x[i]
            grad_b += err
        n = len(training_data)
        for i in range(n_features):
            weights[i] -= lr * grad_w[i] / n
        bias -= lr * grad_b / n

    # MSE на тренировочной выборке — для диагностики (overfit/underfit).
    mse = 0.0
    for x, y in training_data:
        pred = sum(w * f for w, f in zip(weights, x)) + bias
        mse += (pred - y) ** 2
    mse /= len(training_data)

    return {"weights": weights, "bias": bias, "mse": mse}


def predict_delta(features: list[float], model: dict) -> Optional[float]:
    """Предсказать delta funding rate. None если features/model невалидные."""
    if not isinstance(model, dict):
        return None
    weights = model.get("weights") or []
    if not isinstance(weights, list):
        return None
    try:
        bias = float(model.get("bias") or 0.0)
    except (TypeError, ValueError):
        return None
    if not isinstance(features, list) or len(features) != len(weights):
        return None
    try:
        return sum(float(w) * float(f) for w, f in zip(weights, features)) + bias
    except (TypeError, ValueError):
        return None


def to_multiplier(predicted_delta: float, current_rate: float) -> float:
    """Превратить predicted_delta в multiplier ∈ [0.8, 1.3].

    Логика:
    - Если predicted и current в одну сторону (усиливают друг друга) → multiplier > 1.0
    - Если разворачивают → multiplier < 1.0
    - Магнитуда зависит от |predicted_delta| / |current_rate|.

    Безопасно ограничен в [0.8, 1.3] — даже плохой ML не может радикально
    изменить решение executor'а.
    """
    if abs(current_rate) < 1e-9:
        return 1.0  # neutral — нет осмысленного направления

    # Знаки: если совпадают, multiplier > 1; иначе < 1.
    same_direction = (predicted_delta > 0) == (current_rate > 0)

    # Магнитуда — относительно current_rate, ограничена 1.0.
    relative_strength = min(abs(predicted_delta) / abs(current_rate), 1.0)

    if same_direction:
        # 1.0 → 1.3 при relative_strength=0..1
        return 1.0 + 0.3 * relative_strength
    else:
        # 1.0 → 0.8
        return 1.0 - 0.2 * relative_strength


def save_model(model: dict, path: str) -> None:
    """Сохранить модель в JSON."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(model, fh, indent=2)


def load_model(path: str) -> Optional[dict]:
    """Загрузить модель из JSON. None при любой ошибке (graceful fallback)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
