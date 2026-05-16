"""Простая логистическая регрессия для symbol curation.

ML-добавка к rule-based curate_symbols: предсказывает вероятность того,
что символ останется PASS (mean_apr > порога, без спайков) в следующие
30 дней. Обучается на собственной истории funding_snapshots — без HTTP
к внешним сервисам, без heavy deps (numpy не нужен).

Features (6):
  1. mean_apr — средний APR за окно
  2. cv (std/|mean| funding rate) — коэффициент вариации
  3. n_obs / 1000 — нормализованное число наблюдений
  4. n_spike_events_7d / 10 — нормализованное число свежих спайков
  5. % положительных rate — доля бычьего funding
  6. autocorrelation lag-1 — насколько rate "помнит" предыдущий

Target: 1 если в следующие 30 дней символ дал бы PASS
(mean_apr > 0.08 и spikes==0).

Модель — pure-Python (math + statistics). Веса хранятся в JSON,
сохранение/загрузка идемпотентны. При отсутствии модели
``load_model`` вернёт None — потребитель должен fallback'нуться к
правилам без ML.
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timedelta, timezone
from typing import Optional


def extract_features(rows: list[tuple[datetime, float, float]]) -> Optional[list[float]]:
    """Из списка (ts, rate, apr) вытащить 6 фич.

    Возвращает None, если данных меньше 10 — на таком наблюдении статистики
    шумные, лучше пропустить символ.
    """
    if len(rows) < 10:
        return None

    rates = [r[1] for r in rows]
    aprs = [r[2] for r in rows]
    n = len(rows)

    mean_apr = sum(aprs) / n
    mean_rate = sum(rates) / n
    try:
        std_rate = statistics.stdev(rates) if n > 1 else 0.0
    except statistics.StatisticsError:
        std_rate = 0.0
    # Защита от деления на ~0 (mean_rate ≈ 0): кэпим cv на 5.0.
    cv = std_rate / abs(mean_rate) if abs(mean_rate) > 1e-12 else 5.0

    n_obs_norm = min(n / 1000.0, 1.0)

    # Spike events за последние 7 дней (текущий APR > 2.5x mean APR).
    cutoff_7d = datetime.now(tz=timezone.utc) - timedelta(days=7)
    threshold = 2.5 * abs(mean_apr)
    n_spike_7d = sum(
        1 for ts, _r, apr in rows
        if ts >= cutoff_7d and abs(apr) > threshold
    )
    n_spike_norm = min(n_spike_7d / 10.0, 1.0)

    pct_positive = sum(1 for r in rates if r > 0) / n

    # Autocorrelation lag-1.
    if n >= 2:
        diffs = [
            (rates[i] - mean_rate) * (rates[i - 1] - mean_rate)
            for i in range(1, n)
        ]
        var = sum((r - mean_rate) ** 2 for r in rates)
        autocorr = sum(diffs) / var if var > 1e-12 else 0.0
    else:
        autocorr = 0.0
    autocorr = max(-1.0, min(1.0, autocorr))

    return [mean_apr, cv, n_obs_norm, n_spike_norm, pct_positive, autocorr]


def _sigmoid(x: float) -> float:
    """Численно-устойчивый сигмоид."""
    if x < -500:
        return 0.0
    if x > 500:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def train(
    training_data: list[tuple[list[float], int]],
    iterations: int = 1000,
    lr: float = 0.01,
    l2: float = 0.001,
) -> dict:
    """Обучить логистическую регрессию gradient descent'ом.

    training_data: список ``(features, label)``, где features — список
    одинаковой длины, label ∈ {0, 1}.

    Возвращает словарь ``{weights, bias, accuracy}``. accuracy считается
    на тренировочной выборке (для production хочется отдельный val-сет,
    но в нашем сценарии данных мало и это нормально).
    """
    if not training_data:
        return {"weights": [0.0] * 6, "bias": 0.0, "accuracy": 0.0}

    n_features = len(training_data[0][0])
    weights = [0.0] * n_features
    bias = 0.0

    for _ in range(iterations):
        grad_w = [0.0] * n_features
        grad_b = 0.0
        for x, y in training_data:
            z = sum(w * f for w, f in zip(weights, x)) + bias
            p = _sigmoid(z)
            err = p - y
            for i in range(n_features):
                grad_w[i] += err * x[i]
            grad_b += err
        n = len(training_data)
        for i in range(n_features):
            grad_w[i] = grad_w[i] / n + l2 * weights[i]
            weights[i] -= lr * grad_w[i]
        bias -= lr * grad_b / n

    # Считаем accuracy на тренировочном сете.
    correct = 0
    for x, y in training_data:
        p = predict(x, {"weights": weights, "bias": bias})
        pred = 1 if p >= 0.5 else 0
        if pred == y:
            correct += 1
    accuracy = correct / len(training_data) if training_data else 0.0

    return {"weights": weights, "bias": bias, "accuracy": accuracy}


def predict(features: list[float], model: dict) -> float:
    """Вернуть P(symbol будет PASS) ∈ [0, 1].

    Если features не той длины, что weights — возвращаем нейтральное 0.5
    (graceful fallback). На пустой/некорректной модели тоже 0.5.
    """
    if not isinstance(model, dict):
        return 0.5
    weights = model.get("weights") or []
    try:
        bias = float(model.get("bias") or 0.0)
    except (TypeError, ValueError):
        bias = 0.0
    if not isinstance(features, list) or len(features) != len(weights):
        return 0.5
    z = sum(w * f for w, f in zip(weights, features)) + bias
    return _sigmoid(z)


def save_model(model: dict, path: str) -> None:
    """Сериализовать модель в JSON."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(model, fh, indent=2)


def load_model(path: str) -> Optional[dict]:
    """Загрузить модель из JSON. None при любой ошибке (FNF/JSON-decode)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
