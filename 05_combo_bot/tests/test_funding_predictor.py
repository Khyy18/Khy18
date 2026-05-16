"""Тесты funding_predictor: extract_features, train, predict, multiplier."""

import os
from datetime import datetime, timedelta, timezone

import pytest

import funding_predictor


def _mk_history(n_points: int, hours_span: float, base_rate: float = 0.0001):
    """Сгенерировать (ts, rate, apr)-историю на n_points точек за hours_span часов."""
    now = datetime.now(tz=timezone.utc)
    if n_points < 2:
        return []
    step = timedelta(hours=hours_span / (n_points - 1))
    out = []
    for i in range(n_points):
        ts = now - timedelta(hours=hours_span) + i * step
        rate = base_rate + 0.00001 * i  # лёгкий тренд
        apr = rate * 3 * 365
        out.append((ts, rate, apr))
    return out


def test_features_none_when_short_history():
    """< 10 точек → None."""
    hist = _mk_history(5, 24.0)
    assert funding_predictor.extract_features(hist) is None


def test_features_none_when_below_24h():
    """< 24h истории → None, даже если точек много."""
    hist = _mk_history(30, 10.0)  # 30 точек, но всего 10 часов
    assert funding_predictor.extract_features(hist) is None


def test_features_returns_8_floats():
    """30 точек, покрывают 24h → list длины 8 из float'ов."""
    hist = _mk_history(30, 24.0)
    feats = funding_predictor.extract_features(hist)
    assert feats is not None
    assert isinstance(feats, list)
    assert len(feats) == 8
    for f in feats:
        assert isinstance(f, float)


def test_features_empty_history():
    """Пустая история → None."""
    assert funding_predictor.extract_features([]) is None


def test_train_returns_model_dict():
    """Небольшой dataset → model dict с weights/bias/mse."""
    # Простая зависимость: target = 0.1 * sum(features).
    # Маленькие features, чтобы GD сошёлся при lr=0.01.
    training_data = []
    for i in range(20):
        x = [0.01 * (i + j) for j in range(8)]
        y = sum(x) * 0.1
        training_data.append((x, y))
    model = funding_predictor.train(training_data)
    assert isinstance(model, dict)
    assert "weights" in model
    assert "bias" in model
    assert "mse" in model
    assert isinstance(model["weights"], list)
    assert len(model["weights"]) == 8
    # MSE должна быть конечной (не NaN/inf) и достаточно маленькой —
    # GD должен сойтись на простой синтетической зависимости.
    assert model["mse"] >= 0
    assert model["mse"] < 1.0


def test_train_empty_data():
    """Пустой dataset → дефолтная пустая модель."""
    model = funding_predictor.train([])
    assert model["weights"] == [0.0] * 8
    assert model["bias"] == 0.0
    assert model["mse"] == 0.0


def test_predict_delta_returns_float_or_none():
    """Корректные features → float, mismatch → None."""
    model = {"weights": [0.1, 0.2, 0.3], "bias": 0.05, "mse": 0.0}
    # Корректный размер.
    pred = funding_predictor.predict_delta([1.0, 2.0, 3.0], model)
    assert pred is not None
    assert isinstance(pred, float)
    # 0.1*1 + 0.2*2 + 0.3*3 + 0.05 = 1.45
    assert abs(pred - 1.45) < 1e-9
    # Неверный размер.
    assert funding_predictor.predict_delta([1.0, 2.0], model) is None
    # Невалидная модель.
    assert funding_predictor.predict_delta([1.0, 2.0, 3.0], None) is None
    assert funding_predictor.predict_delta([1.0, 2.0, 3.0], "not a dict") is None


def test_multiplier_amplifies_when_aligned():
    """predicted и current одного знака → multiplier > 1.0 (но <= 1.3)."""
    # Оба положительные.
    m = funding_predictor.to_multiplier(predicted_delta=0.5, current_rate=1.0)
    assert m > 1.0
    assert m <= 1.3
    # Оба отрицательные.
    m2 = funding_predictor.to_multiplier(predicted_delta=-0.5, current_rate=-1.0)
    assert m2 > 1.0
    assert m2 <= 1.3


def test_multiplier_dampens_when_opposite():
    """Разные знаки → < 1.0 (но >= 0.8)."""
    m = funding_predictor.to_multiplier(predicted_delta=-0.5, current_rate=1.0)
    assert m < 1.0
    assert m >= 0.8
    m2 = funding_predictor.to_multiplier(predicted_delta=0.5, current_rate=-1.0)
    assert m2 < 1.0
    assert m2 >= 0.8


def test_multiplier_bounded_range():
    """Экстремальные значения → multiplier ∈ [0.8, 1.3]."""
    # Гигантская predicted_delta — relative_strength capped в 1.0.
    m_big_aligned = funding_predictor.to_multiplier(1e9, 0.001)
    assert 0.8 <= m_big_aligned <= 1.3
    m_big_opposite = funding_predictor.to_multiplier(-1e9, 0.001)
    assert 0.8 <= m_big_opposite <= 1.3
    # Точно на границах.
    assert m_big_aligned == 1.3
    assert m_big_opposite == 0.8


def test_multiplier_neutral_when_zero_current():
    """current_rate=0 → 1.0 (нет осмысленного направления)."""
    assert funding_predictor.to_multiplier(0.5, 0.0) == 1.0
    assert funding_predictor.to_multiplier(-0.5, 0.0) == 1.0
    assert funding_predictor.to_multiplier(0.0, 0.0) == 1.0


def test_save_load_roundtrip(tmp_path):
    """save_model + load_model сохраняют всё содержимое."""
    model = {
        "weights": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
        "bias": 0.05,
        "mse": 0.0123,
    }
    path = str(tmp_path / "model.json")
    funding_predictor.save_model(model, path)
    loaded = funding_predictor.load_model(path)
    assert loaded == model


def test_load_model_missing_file_returns_none():
    """Несуществующий файл → None (graceful fallback)."""
    assert funding_predictor.load_model("/tmp/nonexistent_model_12345.json") is None


def test_load_model_corrupt_file_returns_none(tmp_path):
    """Битый JSON → None."""
    path = tmp_path / "bad.json"
    path.write_text("not a json {{{")
    assert funding_predictor.load_model(str(path)) is None
