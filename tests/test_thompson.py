"""Тесты для Thompson Sampling движка."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from ad_testing.thompson import ThompsonSamplingEngine


@pytest.fixture
def ts_engine():
    """Экземпляр ThompsonSamplingEngine."""
    return ThompsonSamplingEngine()


@pytest.fixture
def sample_channels():
    """Тестовые каналы с Beta-параметрами."""
    return [
        {"source_tag": "google_ads", "alpha_param": 10.0, "beta_param": 2.0},
        {"source_tag": "facebook", "alpha_param": 3.0, "beta_param": 8.0},
        {"source_tag": "telegram", "alpha_param": 5.0, "beta_param": 5.0},
    ]


@pytest.fixture
def equal_channels():
    """Каналы с одинаковыми параметрами."""
    return [
        {"source_tag": "ch_a", "alpha_param": 1.0, "beta_param": 1.0},
        {"source_tag": "ch_b", "alpha_param": 1.0, "beta_param": 1.0},
    ]


class TestSampleArm:
    """Тесты сэмплирования из Beta-распределения."""

    def test_sample_in_range(self, ts_engine):
        """Сэмпл из Beta всегда в [0, 1]."""
        for _ in range(100):
            sample = ts_engine.sample_arm(1.0, 1.0)
            assert 0.0 <= sample <= 1.0

    def test_sample_high_alpha(self, ts_engine):
        """При высоком alpha сэмплы ближе к 1."""
        samples = [ts_engine.sample_arm(100.0, 1.0) for _ in range(50)]
        avg = sum(samples) / len(samples)
        assert avg > 0.9

    def test_sample_high_beta(self, ts_engine):
        """При высоком beta сэмплы ближе к 0."""
        samples = [ts_engine.sample_arm(1.0, 100.0) for _ in range(50)]
        avg = sum(samples) / len(samples)
        assert avg < 0.1

    def test_sample_returns_float(self, ts_engine):
        """Возвращается float."""
        sample = ts_engine.sample_arm(2.0, 3.0)
        assert isinstance(sample, float)


class TestSelectBestArm:
    """Тесты выбора лучшего канала."""

    def test_selects_high_alpha_channel(self, ts_engine, sample_channels):
        """Канал с высоким alpha/beta ratio чаще выбирается лучшим."""
        wins = {"google_ads": 0, "facebook": 0, "telegram": 0}
        for _ in range(200):
            best = ts_engine.select_best_arm(sample_channels)
            wins[best] += 1
        # google_ads (alpha=10, beta=2) должен побеждать чаще всего
        assert wins["google_ads"] > wins["facebook"]

    def test_empty_channels(self, ts_engine):
        """При пустом списке возвращает пустую строку."""
        result = ts_engine.select_best_arm([])
        assert result == ""

    def test_single_channel(self, ts_engine):
        """При одном канале возвращает его."""
        channels = [{"source_tag": "only_one", "alpha_param": 1.0, "beta_param": 1.0}]
        result = ts_engine.select_best_arm(channels)
        assert result == "only_one"


class TestUpdateArm:
    """Тесты обновления параметров Beta-распределения."""

    def test_conversion_increments_alpha(self, ts_engine, sample_channels):
        """Конверсия увеличивает alpha на 1."""
        alpha, beta = ts_engine.update_arm("google_ads", True, sample_channels)
        assert alpha == 11.0
        assert beta == 2.0

    def test_no_conversion_increments_beta(self, ts_engine, sample_channels):
        """Отсутствие конверсии увеличивает beta на 1."""
        alpha, beta = ts_engine.update_arm("google_ads", False, sample_channels)
        assert alpha == 10.0
        assert beta == 3.0

    def test_unknown_tag_uses_defaults(self, ts_engine, sample_channels):
        """Неизвестный канал использует defaults (1.0, 1.0)."""
        alpha, beta = ts_engine.update_arm("unknown", True, sample_channels)
        assert alpha == 2.0
        assert beta == 1.0


class TestAllocateBudgetThompson:
    """Тесты распределения бюджета через Thompson Sampling."""

    def test_total_budget_distributed(self, ts_engine, sample_channels):
        """Весь бюджет распределяется между каналами."""
        total = 1000.0
        allocation = ts_engine.allocate_budget_thompson(total, sample_channels)
        assert abs(sum(allocation.values()) - total) < 0.01

    def test_all_channels_get_budget(self, ts_engine, sample_channels):
        """Каждый канал получает ненулевой бюджет."""
        allocation = ts_engine.allocate_budget_thompson(1000.0, sample_channels)
        for tag in ["google_ads", "facebook", "telegram"]:
            assert tag in allocation
            assert allocation[tag] > 0

    def test_empty_channels(self, ts_engine):
        """При пустом списке каналов возвращает пустой словарь."""
        allocation = ts_engine.allocate_budget_thompson(1000.0, [])
        assert allocation == {}

    def test_single_channel_gets_all(self, ts_engine):
        """Один канал получает весь бюджет."""
        channels = [{"source_tag": "solo", "alpha_param": 5.0, "beta_param": 2.0}]
        allocation = ts_engine.allocate_budget_thompson(500.0, channels)
        assert allocation == {"solo": 500.0}

    def test_better_channel_gets_more_on_average(self, ts_engine, sample_channels):
        """Канал с лучшими параметрами в среднем получает больше бюджета."""
        total_google = 0.0
        total_facebook = 0.0
        iterations = 200
        for _ in range(iterations):
            alloc = ts_engine.allocate_budget_thompson(1000.0, sample_channels)
            total_google += alloc.get("google_ads", 0)
            total_facebook += alloc.get("facebook", 0)
        # google_ads (alpha=10, beta=2) должен получать в среднем больше
        assert total_google / iterations > total_facebook / iterations


class TestEngineIntegration:
    """Тесты интеграции Thompson Sampling в ABTestEngine."""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        """Настройка тестовой БД."""
        db_path = str(tmp_path / "test_ad.db")
        with patch.dict(os.environ, {"AD_TESTING_DB_PATH": db_path}):
            with patch("ad_testing.models.DB_PATH", db_path):
                from ad_testing import models
                from ad_testing.engine import ABTestEngine

                models.DB_PATH = db_path
                self.engine = ABTestEngine()
                self.models = models
                yield

    def test_allocate_budget_thompson(self):
        """allocate_budget_thompson работает через ABTestEngine."""
        self.engine.register_channel("Google Ads", "google")
        self.engine.register_channel("Facebook", "fb")

        allocation = self.engine.allocate_budget_thompson(1000.0)
        assert len(allocation) == 2
        assert abs(sum(allocation.values()) - 1000.0) < 0.01

    def test_record_event_thompson_updates_params(self):
        """record_event_thompson обновляет Beta-параметры."""
        self.engine.register_channel("Test Channel", "test_ch")
        self.engine.record_event_thompson("test_ch", "conversion", revenue=100.0)

        alpha, beta = self.models.get_beta_params("test_ch")
        assert alpha == 2.0  # 1.0 (default) + 1 (conversion)
        assert beta == 1.0   # не изменилась

    def test_record_event_thompson_click(self):
        """record_event_thompson при click увеличивает beta."""
        self.engine.register_channel("Click Channel", "click_ch")
        self.engine.record_event_thompson("click_ch", "click")

        alpha, beta = self.models.get_beta_params("click_ch")
        assert alpha == 1.0   # не изменилась
        assert beta == 2.0    # 1.0 (default) + 1 (not conversion)

    def test_record_event_thompson_impression_no_update(self):
        """impression не обновляет Beta-параметры."""
        self.engine.register_channel("Impr Channel", "impr_ch")
        self.engine.record_event_thompson("impr_ch", "impression")

        alpha, beta = self.models.get_beta_params("impr_ch")
        assert alpha == 1.0
        assert beta == 1.0
