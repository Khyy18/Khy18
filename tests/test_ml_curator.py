"""Тесты ml_curator: features, train, predict, save/load."""

from __future__ import annotations

import os
import random
from datetime import datetime, timedelta, timezone

import ml_curator


def _fake_rows(n: int, base_apr: float = 0.10) -> list:
    """Сгенерировать n синтетических (ts, rate, apr) с лёгким шумом."""
    rng = random.Random(42)
    now = datetime.now(tz=timezone.utc)
    rows = []
    for i in range(n):
        ts = now - timedelta(hours=i)
        apr = base_apr + rng.gauss(0.0, 0.01)
        rate = apr / (365 * 3)  # ~3 funding-tick в сутки
        rows.append((ts, rate, apr))
    return rows


def test_extract_features_returns_6_floats():
    """50 синтетических rows -> features длины 6, все float."""
    rows = _fake_rows(50)
    features = ml_curator.extract_features(rows)
    assert features is not None
    assert isinstance(features, list)
    assert len(features) == 6
    for f in features:
        assert isinstance(f, float)


def test_extract_features_none_when_short():
    """5 rows < 10 -> None."""
    rows = _fake_rows(5)
    assert ml_curator.extract_features(rows) is None


def test_train_converges_on_synthetic():
    """Линейно-разделимый dataset: target = 1 если features[0] > 0.5.

    После train accuracy должна быть > 0.85.
    """
    rng = random.Random(123)
    training_data = []
    for _ in range(100):
        feat = [rng.uniform(0.0, 1.0) for _ in range(6)]
        label = 1 if feat[0] > 0.5 else 0
        training_data.append((feat, label))
    model = ml_curator.train(training_data, iterations=2000, lr=0.05)
    assert model["accuracy"] > 0.85


def test_predict_in_unit_interval():
    """Для случайных features вероятность ∈ [0, 1]."""
    rng = random.Random(7)
    model = {
        "weights": [rng.uniform(-2, 2) for _ in range(6)],
        "bias": rng.uniform(-1, 1),
    }
    for _ in range(20):
        feat = [rng.uniform(-1, 1) for _ in range(6)]
        p = ml_curator.predict(feat, model)
        assert 0.0 <= p <= 1.0


def test_save_load_roundtrip(tmp_path):
    """Сохраняем модель и загружаем — должны совпасть веса/bias/accuracy."""
    model = {
        "weights": [0.1, -0.2, 0.3, -0.4, 0.5, -0.6],
        "bias": 0.123,
        "accuracy": 0.91,
    }
    path = str(tmp_path / "test_model.json")
    ml_curator.save_model(model, path)
    loaded = ml_curator.load_model(path)
    assert loaded is not None
    assert loaded["weights"] == model["weights"]
    assert loaded["bias"] == model["bias"]
    assert loaded["accuracy"] == model["accuracy"]


def test_load_returns_none_when_missing():
    """Несуществующий файл -> None."""
    assert ml_curator.load_model("/nonexistent/path/no_such_model.json") is None


def test_predict_neutral_on_invalid_features():
    """Mismatched length features → 0.5 (нейтральный fallback)."""
    model = {"weights": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "bias": 0.0}
    p = ml_curator.predict([0.5, 0.5], model)  # 2 элемента, надо 6
    assert p == 0.5
