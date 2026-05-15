"""Тесты anomaly_detector: MetricTracker и AnomalyDetector."""

import time

import pytest

import anomaly_detector


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Сбросить глобальный singleton перед каждым тестом."""
    anomaly_detector.reset_detector()
    yield
    anomaly_detector.reset_detector()


# --- MetricTracker ----------------------------------------------------

def test_metric_tracker_no_alert_in_warmup():
    """Первые 9 значений → None (warm-up <10 точек)."""
    tracker = anomaly_detector.MetricTracker(window_size=100)
    for i in range(9):
        z = tracker.add(float(i))
        assert z is None, f"warm-up должен быть None, но на i={i} вернул {z}"


def test_metric_tracker_z_score_normal_range():
    """100 значений около 1.0 ± 0.1, потом 1.05 → |z| < 1."""
    tracker = anomaly_detector.MetricTracker(window_size=200)
    # 100 значений, симметрично около 1.0, std ≈ 0.1.
    base_values = [1.0 + 0.1 * (i - 50) / 50.0 for i in range(100)]
    for v in base_values:
        tracker.add(v)
    # Контрольное значение чуть выше среднего — z должно быть маленьким.
    z = tracker.add(1.05)
    assert z is not None
    assert abs(z) < 1.5, f"|z| должно быть < 1.5 для значения близко к mean, получено {z}"


def test_metric_tracker_detects_3sigma_outlier():
    """100 значений около 1.0 ± 0.1, потом 5.0 → z >> 3."""
    tracker = anomaly_detector.MetricTracker(window_size=200)
    # Значения 0.9..1.1, std ≈ 0.06.
    for i in range(100):
        tracker.add(1.0 + 0.1 * ((i % 5) - 2) / 2.0)
    z = tracker.add(5.0)
    assert z is not None
    assert z > 30, f"Значение 5.0 при mean≈1.0 std≈0.06 должно дать z > 30, получено {z}"


def test_metric_tracker_handles_nan():
    """NaN не должен ломать tracker."""
    tracker = anomaly_detector.MetricTracker()
    z = tracker.add(float("nan"))
    assert z is None
    # Все ок — добавление продолжается.
    for i in range(15):
        tracker.add(1.0)
    z2 = tracker.add(1.0)
    assert z2 is not None


def test_metric_tracker_window_rotation():
    """Окно длиной 20: добавляем 100 значений, mean пересчитывается."""
    tracker = anomaly_detector.MetricTracker(window_size=20)
    # Сначала 20 раз 0.0.
    for _ in range(20):
        tracker.add(0.0)
    assert abs(tracker.mean()) < 1e-9
    # Заменяем все на 10.0 (после rotation).
    for _ in range(20):
        tracker.add(10.0)
    assert abs(tracker.mean() - 10.0) < 1e-6


# --- AnomalyDetector --------------------------------------------------

def test_detector_returns_none_below_threshold():
    """Ниже threshold → None (нет алерта)."""
    detector = anomaly_detector.AnomalyDetector(threshold=3.0, window_size=100)
    # Имитируем шумные значения с большим std, чтобы 1.05 не было выбросом.
    import random
    rng = random.Random(42)
    for _ in range(50):
        v = 1.0 + rng.gauss(0.0, 0.5)  # std ≈ 0.5
        detector.record("test_metric", v)
    # Контрольное значение в пределах 1σ — не должен сработать.
    result = detector.record("test_metric", 1.05)
    assert result is None


def test_detector_alerts_on_breach():
    """Выше threshold → возвращает dict с метаданными."""
    detector = anomaly_detector.AnomalyDetector(
        threshold=3.0, window_size=200, alert_cooldown_sec=0.0,
    )
    for i in range(100):
        detector.record("response_time", 100.0 + 0.5 * ((i % 5) - 2))
    result = detector.record("response_time", 500.0)
    assert result is not None
    assert result["metric"] == "response_time"
    assert result["value"] == 500.0
    assert abs(result["z_score"]) > 3.0
    assert "mean" in result
    assert "std" in result


def test_detector_cooldown_blocks_repeat():
    """Два выброса подряд → alert только на первый (cooldown)."""
    detector = anomaly_detector.AnomalyDetector(
        threshold=3.0, window_size=200, alert_cooldown_sec=3600.0,
    )
    for i in range(100):
        detector.record("metric", 1.0 + 0.01 * (i % 3))
    first = detector.record("metric", 100.0)  # явный выброс
    assert first is not None
    # Сразу повторяем — cooldown активен.
    second = detector.record("metric", 100.0)
    assert second is None


def test_detector_cooldown_separate_signs():
    """Положительный и отрицательный выбросы — независимые cooldown'ы."""
    detector = anomaly_detector.AnomalyDetector(
        threshold=3.0, window_size=200, alert_cooldown_sec=3600.0,
    )
    for i in range(100):
        detector.record("metric", 1.0 + 0.01 * (i % 3))
    pos = detector.record("metric", 100.0)
    assert pos is not None
    # Отрицательный выброс — отдельный cooldown.
    neg = detector.record("metric", -100.0)
    assert neg is not None
    assert pos["z_score"] > 0
    assert neg["z_score"] < 0


def test_status_lists_all_metrics():
    """status() возвращает все известные трекеры."""
    detector = anomaly_detector.AnomalyDetector()
    detector.record("a", 1.0)
    detector.record("b", 2.0)
    snap = detector.status()
    assert "a" in snap
    assert "b" in snap
    assert snap["a"]["n_samples"] == 1
    assert snap["b"]["n_samples"] == 1


def test_reset_clears_tracker():
    """reset() очищает один или все трекеры."""
    detector = anomaly_detector.AnomalyDetector()
    detector.record("a", 1.0)
    detector.record("b", 2.0)
    detector.reset("a")
    assert "a" not in detector.status()
    assert "b" in detector.status()
    detector.reset()  # без аргумента — всё.
    assert detector.status() == {}


def test_global_detector_is_singleton():
    """get_detector() всегда возвращает один и тот же объект."""
    d1 = anomaly_detector.get_detector()
    d2 = anomaly_detector.get_detector()
    assert d1 is d2
    # И reset_detector() реально пересоздаёт.
    anomaly_detector.reset_detector()
    d3 = anomaly_detector.get_detector()
    assert d3 is not d1
