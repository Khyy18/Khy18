"""Тесты для модуля A/B-тестирования рекламных каналов (ad_testing)."""
from __future__ import annotations

import os
import sqlite3
from unittest.mock import patch

import pytest


# --- Тесты chi-squared ---


def test_chi_squared_known_values():
    """Chi-squared тест с известными значениями: значимое различие."""
    from ad_testing.stats import chi_squared_test

    # Канал A: 80 конверсий из 1000 кликов (8%)
    # Канал B: 50 конверсий из 1000 кликов (5%)
    chi2, p_value = chi_squared_test(80, 1000, 50, 1000)

    # p-value должен быть значимым (< 0.05)
    assert chi2 > 0
    assert p_value < 0.05


def test_chi_squared_identical_rates():
    """Одинаковые конверсионные ставки - не значимо."""
    from ad_testing.stats import chi_squared_test

    # Оба канала: 10% конверсия
    chi2, p_value = chi_squared_test(100, 1000, 100, 1000)

    assert chi2 == 0.0
    assert p_value == 1.0


def test_chi_squared_zero_trials():
    """Нулевые trials - граничный случай, возвращает (0, 1)."""
    from ad_testing.stats import chi_squared_test

    chi2, p_value = chi_squared_test(10, 0, 5, 100)
    assert chi2 == 0.0
    assert p_value == 1.0

    chi2, p_value = chi_squared_test(10, 100, 5, 0)
    assert chi2 == 0.0
    assert p_value == 1.0


# --- Тесты models + engine ---


@pytest.fixture
def ad_db(tmp_path):
    """Фикстура: временная БД для ad_testing."""
    db_path = str(tmp_path / "test_ad.db")
    with patch("ad_testing.models.DB_PATH", db_path):
        from ad_testing import models
        models.init_db()
        yield db_path


def test_register_channel_and_record_event(ad_db):
    """Регистрация канала и запись событий."""
    with patch("ad_testing.models.DB_PATH", ad_db):
        from ad_testing import models

        ch_id = models.register_channel("Яндекс.Директ", "ya_direct")
        assert ch_id is not None
        assert ch_id > 0

        # Запись кликов
        models.record_event("ya_direct", "click")
        models.record_event("ya_direct", "click")
        models.record_event("ya_direct", "click")

        # Запись конверсии
        models.record_event("ya_direct", "conversion", revenue=150.0)

        # Запись показов
        models.record_event("ya_direct", "impression")
        models.record_event("ya_direct", "impression")

        stats = models.get_channel_stats("ya_direct")
        assert stats is not None
        assert stats["clicks"] == 3
        assert stats["conversions"] == 1
        assert stats["revenue"] == 150.0
        assert stats["impressions"] == 2


def test_allocate_budget_80_20_split(ad_db):
    """Распределение бюджета: 80% лучшим, 20% экспериментальным."""
    with patch("ad_testing.models.DB_PATH", ad_db):
        from ad_testing.engine import ABTestEngine

        engine = ABTestEngine()

        # Канал A: высокая конверсия (50%)
        engine.register_channel("Канал A", "channel_a")
        for _ in range(100):
            engine.record_event("channel_a", "click")
        for _ in range(50):
            engine.record_event("channel_a", "conversion", revenue=10.0)

        # Канал B: низкая конверсия (10%)
        engine.register_channel("Канал B", "channel_b")
        for _ in range(100):
            engine.record_event("channel_b", "click")
        for _ in range(10):
            engine.record_event("channel_b", "conversion", revenue=5.0)

        allocation = engine.allocate_budget(1000.0)

        assert "channel_a" in allocation
        assert "channel_b" in allocation

        # Лучший канал получает 80% = 800
        assert allocation["channel_a"] == pytest.approx(800.0)
        # Экспериментальный получает 20% = 200
        assert allocation["channel_b"] == pytest.approx(200.0)

        # Сумма = 100%
        total = sum(allocation.values())
        assert total == pytest.approx(1000.0)


def test_compute_significance_returns_winner(ad_db):
    """compute_significance определяет победителя при значимой разнице."""
    with patch("ad_testing.models.DB_PATH", ad_db):
        from ad_testing.engine import ABTestEngine

        engine = ABTestEngine()

        # Канал A: 80 конверсий из 1000 кликов (8%)
        engine.register_channel("Канал A", "sig_a")
        for _ in range(1000):
            engine.record_event("sig_a", "click")
        for _ in range(80):
            engine.record_event("sig_a", "conversion")

        # Канал B: 50 конверсий из 1000 кликов (5%)
        engine.register_channel("Канал B", "sig_b")
        for _ in range(1000):
            engine.record_event("sig_b", "click")
        for _ in range(50):
            engine.record_event("sig_b", "conversion")

        result = engine.compute_significance("sig_a", "sig_b")

        assert result["chi2"] > 0
        assert result["p_value"] < 0.05
        assert result["is_significant"] is True
        assert result["winner"] == "sig_a"
        assert result["conversion_rate_a"] == pytest.approx(0.08)
        assert result["conversion_rate_b"] == pytest.approx(0.05)


def test_dashboard_data_structure(ad_db):
    """get_dashboard_data возвращает корректную структуру данных."""
    with patch("ad_testing.models.DB_PATH", ad_db):
        from ad_testing.engine import ABTestEngine

        engine = ABTestEngine()
        engine.register_channel("Тест", "dash_test")
        engine.record_event("dash_test", "impression")
        engine.record_event("dash_test", "click")
        engine.record_event("dash_test", "conversion", revenue=100.0)

        data = engine.get_dashboard_data()

        assert "channels" in data
        assert "total_channels" in data
        assert data["total_channels"] == 1

        ch = data["channels"][0]
        assert ch["name"] == "Тест"
        assert ch["source_tag"] == "dash_test"
        assert ch["impressions"] == 1
        assert ch["clicks"] == 1
        assert ch["conversions"] == 1
        assert ch["revenue"] == 100.0
        assert "ctr" in ch
        assert "conversion_rate" in ch
