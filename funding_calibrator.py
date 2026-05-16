"""Калибратор funding-PnL оценки через ML.

Идея: когда API биржи не отдаёт реальные funding-выплаты (MEXC, HTX),
бот считает аналитически: rate × notional × delta_h. Эта оценка
отличается от реального на 5-20%.

Этот модуль обучает коэффициент коррекции на данных бирж, где реальный
PnL ИЗВЕСТЕН (Bybit/OKX/Binance): features → predicted_correction_factor.

Runtime: estimated_funding * get_correction_factor(features) = calibrated.

Пока модель не обучена — возвращает 1.0 (neutral, как сейчас).

Обучение запускается через train_calibrator.py (после 30+ дней сбора
данных с Bybit/OKX/Binance).
"""

from __future__ import annotations

import json
from typing import Optional


_MODEL_PATH = "funding_calibrator_model.json"
_MODEL: Optional[dict] = None


def _load() -> Optional[dict]:
    """Загрузить модель из JSON-файла (lazy singleton)."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        with open(_MODEL_PATH, "r", encoding="utf-8") as f:
            _MODEL = json.load(f)
            return _MODEL
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def get_correction_factor(
    exchange: str,
    symbol: str,
    held_hours: float,
    rate_at_open: float,
    rate_at_close: float,
    mark_price_change_pct: float,
) -> float:
    """Вернуть коэффициент коррекции для аналитической оценки funding.

    1.0 = без коррекции (модель не загружена или fallback).
    < 1.0 = реальная выплата обычно меньше оценки.
    > 1.0 = реальная выплата обычно больше.

    Bounded в [0.7, 1.3] — даже плохая модель не может сильно исказить PnL.
    """
    model = _load()
    if model is None:
        return 1.0

    # Features: exchange_id, held_hours_norm, rate_magnitude, price_change.
    exchange_map: dict[str, float] = model.get("exchange_map") or {}
    weights: list[float] = model.get("weights") or []
    bias: float = float(model.get("bias") or 0.0)

    if not weights:
        return 1.0

    ex_id = float(exchange_map.get(exchange.lower(), 0.5))
    features: list[float] = [
        ex_id,
        min(held_hours / 168.0, 1.0),  # normalized to max 1 week
        abs(rate_at_open) * 10000,  # scale up small rates
        abs(rate_at_close - rate_at_open) * 10000,
        abs(mark_price_change_pct),
    ]

    if len(features) != len(weights):
        return 1.0

    prediction: float = sum(w * f for w, f in zip(weights, features)) + bias
    # Bound в [0.7, 1.3].
    return max(0.7, min(1.3, prediction))


def reset() -> None:
    """Сброс кэшированной модели (для тестов)."""
    global _MODEL
    _MODEL = None
