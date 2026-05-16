"""PricingModel: динамическое ценообразование на основе множества факторов.

Факторы:
  - time_of_day (0-23 час UTC)
  - workload (количество текущих открытых заказов)
  - service_type (тип услуги)
  - client_history (повторный клиент - скидка)
"""

from __future__ import annotations

from logging_config import get_logger

log = get_logger(__name__)

# Премиальные типы услуг
_PREMIUM_SERVICES = {"ai", "ml", "blockchain", "security", "architecture"}


class PricingModel:
    """Модель динамического ценообразования. Возвращает мультипликатор 0.8-1.5."""

    def __init__(
        self,
        peak_hour_start: int = 10,
        peak_hour_end: int = 18,
        high_workload_threshold: int = 5,
    ) -> None:
        self.peak_hour_start = peak_hour_start
        self.peak_hour_end = peak_hour_end
        self.high_workload_threshold = high_workload_threshold

    def compute_multiplier(self, factors: dict) -> float:
        """Вычислить ценовой мультипликатор на основе факторов.

        Args:
            factors: словарь с ключами:
                - time_of_day: int (0-23, час UTC)
                - workload: int (количество открытых заказов)
                - service_type: str (тип услуги)
                - client_history: bool (True если повторный клиент)

        Returns:
            Мультипликатор в диапазоне 0.8-1.5.
        """
        multiplier = 1.0

        # Пиковые часы (10-18 UTC) -> +10%
        hour = int(factors.get("time_of_day", 12))
        if self.peak_hour_start <= hour < self.peak_hour_end:
            multiplier *= 1.1

        # Высокая нагрузка (>5 заказов) -> +20%
        workload = int(factors.get("workload", 0))
        if workload > self.high_workload_threshold:
            multiplier *= 1.2

        # Повторный клиент -> -10%
        if factors.get("client_history", False):
            multiplier *= 0.9

        # Премиальный сервис -> +30%
        service_type = str(factors.get("service_type", "")).lower()
        if service_type in _PREMIUM_SERVICES:
            multiplier *= 1.3

        # Ограничить диапазон 0.8-1.5
        multiplier = max(0.8, min(1.5, multiplier))

        log.info(
            "pricing_multiplier_computed",
            multiplier=round(multiplier, 3),
            factors=factors,
        )
        return round(multiplier, 3)
