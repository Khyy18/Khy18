"""Тесты для модуля Pricing."""
from __future__ import annotations

from unittest.mock import patch

import pytest


# --- Тесты PricingModel ---


def test_compute_multiplier_peak_hours():
    """PricingModel: пиковые часы увеличивают мультипликатор."""
    from pricing.model import PricingModel

    model = PricingModel()

    # Пиковый час (12:00 UTC)
    result_peak = model.compute_multiplier({
        "time_of_day": 12,
        "workload": 0,
        "service_type": "web",
        "client_history": False,
    })

    # Непиковый час (22:00 UTC)
    result_offpeak = model.compute_multiplier({
        "time_of_day": 22,
        "workload": 0,
        "service_type": "web",
        "client_history": False,
    })

    assert result_peak > result_offpeak


def test_compute_multiplier_high_workload():
    """PricingModel: высокая нагрузка увеличивает мультипликатор."""
    from pricing.model import PricingModel

    model = PricingModel()

    # Высокая нагрузка (8 заказов)
    result_high = model.compute_multiplier({
        "time_of_day": 22,
        "workload": 8,
        "service_type": "web",
        "client_history": False,
    })

    # Низкая нагрузка (2 заказа)
    result_low = model.compute_multiplier({
        "time_of_day": 22,
        "workload": 2,
        "service_type": "web",
        "client_history": False,
    })

    assert result_high > result_low


def test_compute_multiplier_repeat_client():
    """PricingModel: повторный клиент получает скидку."""
    from pricing.model import PricingModel

    model = PricingModel()

    # Новый клиент
    result_new = model.compute_multiplier({
        "time_of_day": 22,
        "workload": 0,
        "service_type": "web",
        "client_history": False,
    })

    # Повторный клиент
    result_repeat = model.compute_multiplier({
        "time_of_day": 22,
        "workload": 0,
        "service_type": "web",
        "client_history": True,
    })

    assert result_repeat < result_new


def test_compute_multiplier_premium_service():
    """PricingModel: премиальный сервис увеличивает цену."""
    from pricing.model import PricingModel

    model = PricingModel()

    # Обычный сервис
    result_regular = model.compute_multiplier({
        "time_of_day": 22,
        "workload": 0,
        "service_type": "web",
        "client_history": False,
    })

    # Премиальный сервис
    result_premium = model.compute_multiplier({
        "time_of_day": 22,
        "workload": 0,
        "service_type": "ai",
        "client_history": False,
    })

    assert result_premium > result_regular


def test_compute_multiplier_bounds():
    """PricingModel: мультипликатор всегда в диапазоне 0.8-1.5."""
    from pricing.model import PricingModel

    model = PricingModel()

    # Максимальные факторы
    result_max = model.compute_multiplier({
        "time_of_day": 12,
        "workload": 10,
        "service_type": "ai",
        "client_history": False,
    })

    # Минимальные факторы (повторный, непик, нет нагрузки, обычный сервис)
    result_min = model.compute_multiplier({
        "time_of_day": 3,
        "workload": 0,
        "service_type": "web",
        "client_history": True,
    })

    assert 0.8 <= result_max <= 1.5
    assert 0.8 <= result_min <= 1.5


# --- Тесты PricingOptimizer ---


def test_optimizer_converges():
    """PricingOptimizer: revenue улучшается за итерации."""
    from pricing.optimizer import PricingOptimizer, _compute_revenue

    historical_data = [
        {"base_price": 10000, "factors": {"time_of_day": 0.5, "workload": 0.3, "service_premium": 0.2}, "converted": True},
        {"base_price": 15000, "factors": {"time_of_day": 0.8, "workload": 0.1, "service_premium": 0.5}, "converted": True},
        {"base_price": 8000, "factors": {"time_of_day": 0.2, "workload": 0.7, "service_premium": 0.0}, "converted": False},
        {"base_price": 20000, "factors": {"time_of_day": 0.9, "workload": 0.2, "service_premium": 0.8}, "converted": True},
        {"base_price": 5000, "factors": {"time_of_day": 0.1, "workload": 0.9, "service_premium": 0.1}, "converted": True},
    ]

    # Baseline с нулевыми весами
    baseline_weights = {"time_of_day": 0.0, "workload": 0.0, "service_premium": 0.0}
    baseline_revenue = _compute_revenue(baseline_weights, historical_data)

    # Оптимизированные веса
    optimizer = PricingOptimizer(n_iterations=200, perturbation=0.1)
    optimized_weights = optimizer.optimize_weights(historical_data)

    optimized_revenue = _compute_revenue(optimized_weights, historical_data)

    # Оптимизированный revenue >= baseline (может быть равен при плохом seed)
    assert optimized_revenue >= baseline_revenue


def test_optimizer_empty_data():
    """PricingOptimizer: пустые данные возвращают дефолтные веса."""
    from pricing.optimizer import PricingOptimizer

    optimizer = PricingOptimizer()
    weights = optimizer.optimize_weights([])

    assert isinstance(weights, dict)
    assert len(weights) > 0


# --- Тесты get_price ---


def test_get_price_applies_multiplier():
    """get_price применяет мультипликатор к базовой цене."""
    with patch("config.PRICING_BASE_MULTIPLIER", 1.0):
        from pricing.service import get_price

        price = get_price(10000.0, "web", client_tg_id=None)

        # Цена должна быть в разумном диапазоне (base * 0.8 to base * 1.5)
        assert 8000.0 <= price <= 15000.0


def test_get_price_premium_service():
    """get_price: премиальный сервис дороже обычного."""
    with patch("config.PRICING_BASE_MULTIPLIER", 1.0):
        from pricing.service import get_price

        price_regular = get_price(10000.0, "web", client_tg_id=None)
        price_premium = get_price(10000.0, "ai", client_tg_id=None)

        assert price_premium > price_regular


def test_get_price_with_repeat_client():
    """get_price: повторный клиент получает скидку."""
    with patch("config.PRICING_BASE_MULTIPLIER", 1.0):
        from pricing.service import get_price

        price_new = get_price(10000.0, "web", client_tg_id=None)
        price_repeat = get_price(10000.0, "web", client_tg_id=12345)

        assert price_repeat < price_new
