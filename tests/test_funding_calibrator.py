"""Тесты funding_calibrator: neutral без модели, bounded, reset."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import funding_calibrator


@pytest.fixture(autouse=True)
def _reset_model():
    """Сбрасываем кэш модели перед каждым тестом."""
    funding_calibrator.reset()
    yield
    funding_calibrator.reset()


def test_correction_factor_neutral_without_model():
    """Нет файла модели → возвращает 1.0 (neutral)."""
    # Файла funding_calibrator_model.json не существует.
    factor = funding_calibrator.get_correction_factor(
        exchange="mexc",
        symbol="BTCUSDT",
        held_hours=48.0,
        rate_at_open=0.0001,
        rate_at_close=0.00015,
        mark_price_change_pct=2.5,
    )
    assert factor == 1.0


def test_correction_factor_bounded(tmp_path, monkeypatch):
    """С моделью и экстремальными features результат в [0.7, 1.3]."""
    # Создаём модель с большими весами, чтобы prediction вышел за [0.7, 1.3].
    model = {
        "exchange_map": {"mexc": 0.8, "htx": 0.6},
        "weights": [10.0, 10.0, 10.0, 10.0, 10.0],  # Большие веса → большой prediction.
        "bias": 5.0,
    }
    model_path = str(tmp_path / "model.json")
    with open(model_path, "w") as f:
        json.dump(model, f)

    # Подменяем путь к модели.
    monkeypatch.setattr(funding_calibrator, "_MODEL_PATH", model_path)

    factor = funding_calibrator.get_correction_factor(
        exchange="mexc",
        symbol="BTCUSDT",
        held_hours=200.0,
        rate_at_open=0.01,
        rate_at_close=0.02,
        mark_price_change_pct=50.0,
    )
    # Должен быть bounded до 1.3 (prediction будет огромным).
    assert factor == 1.3

    # Теперь модель с отрицательными весами → prediction будет маленьким.
    funding_calibrator.reset()
    model_neg = {
        "exchange_map": {"mexc": 0.1},
        "weights": [-10.0, -10.0, -10.0, -10.0, -10.0],
        "bias": -5.0,
    }
    with open(model_path, "w") as f:
        json.dump(model_neg, f)

    factor_low = funding_calibrator.get_correction_factor(
        exchange="mexc",
        symbol="ETHUSDT",
        held_hours=100.0,
        rate_at_open=0.005,
        rate_at_close=0.01,
        mark_price_change_pct=30.0,
    )
    # Должен быть bounded до 0.7 (prediction будет сильно отрицательным).
    assert factor_low == 0.7


def test_reset_clears_cache(tmp_path, monkeypatch):
    """После reset() модуль заново пытается загрузить модель."""
    # Сначала нет файла — factor == 1.0.
    model_path = str(tmp_path / "model.json")
    monkeypatch.setattr(funding_calibrator, "_MODEL_PATH", model_path)

    factor_before = funding_calibrator.get_correction_factor(
        exchange="bybit", symbol="SOLUSDT",
        held_hours=10.0, rate_at_open=0.0001,
        rate_at_close=0.0002, mark_price_change_pct=1.0,
    )
    assert factor_before == 1.0

    # Теперь создаём файл модели.
    model = {
        "exchange_map": {"bybit": 0.3},
        "weights": [0.2, 0.1, 0.05, 0.05, 0.1],
        "bias": 0.9,
    }
    with open(model_path, "w") as f:
        json.dump(model, f)

    # Без reset — по-прежнему 1.0 (кэш None означает "не нашли").
    # Нужно сбросить и перечитать.
    funding_calibrator.reset()

    factor_after = funding_calibrator.get_correction_factor(
        exchange="bybit", symbol="SOLUSDT",
        held_hours=10.0, rate_at_open=0.0001,
        rate_at_close=0.0002, mark_price_change_pct=1.0,
    )
    # Теперь модель загружена — factor != 1.0 (вычисляется по формуле).
    # С данными весами: 0.3*0.2 + (10/168)*0.1 + 0.001*0.05 + 0.001*0.05 + 1.0*0.1 + 0.9
    # ≈ 0.06 + 0.006 + 0.00005 + 0.00005 + 0.1 + 0.9 = 1.0661
    # Bounded: остаётся в [0.7, 1.3] → ≈ 1.066
    assert 0.7 <= factor_after <= 1.3
    assert factor_after != 1.0
