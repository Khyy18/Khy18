"""PricingOptimizer: gradient-free optimization для ценообразования.

Использует random search с perturbation для оптимизации весов факторов.
Максимизирует revenue = sum(price * conversion_probability).
"""

from __future__ import annotations

import random
from typing import Any

from logging_config import get_logger

log = get_logger(__name__)


def _compute_revenue(
    weights: dict[str, float], historical_data: list[dict]
) -> float:
    """Вычислить суммарный revenue для набора весов.

    Каждая запись в historical_data содержит:
        - base_price: float
        - factors: dict (time_of_day, workload, service_type, client_history)
        - converted: bool (была ли конверсия)
    """
    total_revenue = 0.0

    for record in historical_data:
        base_price = float(record.get("base_price", 0))
        factors = record.get("factors", {})

        # Вычислить мультипликатор на основе весов
        multiplier = 1.0
        for factor_name, weight in weights.items():
            if factor_name in factors:
                factor_val = float(factors[factor_name]) if isinstance(
                    factors[factor_name], (int, float)
                ) else (1.0 if factors[factor_name] else 0.0)
                multiplier += weight * factor_val

        # Ограничить 0.8-1.5
        multiplier = max(0.8, min(1.5, multiplier))
        price = base_price * multiplier

        # Простая модель: вероятность конверсии падает с ростом цены
        # Если converted=True, считаем revenue = price
        if record.get("converted", False):
            total_revenue += price

    return total_revenue


class PricingOptimizer:
    """Оптимизатор ценообразования через gradient-free random search."""

    def __init__(self, n_iterations: int = 100, perturbation: float = 0.1) -> None:
        self.n_iterations = n_iterations
        self.perturbation = perturbation

    def optimize_weights(self, historical_data: list[dict]) -> dict[str, float]:
        """Оптимизировать веса факторов на исторических данных.

        Args:
            historical_data: список словарей с base_price, factors, converted.

        Returns:
            Оптимальные веса факторов.
        """
        if not historical_data:
            return {"time_of_day": 0.01, "workload": 0.02, "service_premium": 0.03}

        # Начальные веса
        weights: dict[str, float] = {
            "time_of_day": 0.01,
            "workload": 0.02,
            "service_premium": 0.03,
        }

        best_revenue = _compute_revenue(weights, historical_data)
        best_weights = dict(weights)

        for iteration in range(self.n_iterations):
            # Перетурбация: случайное изменение одного веса
            candidate = dict(best_weights)
            key = random.choice(list(candidate.keys()))
            delta = random.uniform(-self.perturbation, self.perturbation)
            candidate[key] = candidate[key] + delta

            # Ограничить веса разумным диапазоном
            candidate[key] = max(-0.5, min(0.5, candidate[key]))

            revenue = _compute_revenue(candidate, historical_data)

            if revenue > best_revenue:
                best_revenue = revenue
                best_weights = candidate

        log.info(
            "pricing_optimization_complete",
            iterations=self.n_iterations,
            best_revenue=round(best_revenue, 2),
            best_weights=best_weights,
        )
        return best_weights
