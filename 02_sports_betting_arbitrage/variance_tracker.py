"""Трекер дисперсии результатов ставок.

Отслеживает running variance, детектирует аномальные серии,
рекомендует снижение Kelly при повышенной волатильности.
"""

from __future__ import annotations

import logging
import math
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)


class VarianceTracker:
    """Отслеживание дисперсии результатов."""

    def __init__(self, window_size: int = 50) -> None:
        self._window_size = window_size
        self._values: deque[float] = deque(maxlen=window_size)
        self._historical_sigma: float = 2.0  # default historical sigma

    def update(self, pnl_value: float) -> None:
        """Add a new PnL result to the rolling window."""
        self._values.append(pnl_value)

    def get_variance(self) -> float:
        """Return running variance over the window. 0.0 if < 2 values."""
        if len(self._values) < 2:
            return 0.0
        mean = sum(self._values) / len(self._values)
        variance = sum((x - mean) ** 2 for x in self._values) / len(self._values)
        return round(variance, 4)

    def get_std(self) -> float:
        """Return standard deviation."""
        v = self.get_variance()
        return round(math.sqrt(v), 4) if v > 0 else 0.0

    def get_status(self) -> str:
        """Return variance status: 'normal', 'high', 'critical'.

        Compares current std to historical_sigma:
        - normal: std <= 1.5 * historical_sigma
        - high: 1.5 * historical_sigma < std <= 2.0 * historical_sigma
        - critical: std > 2.0 * historical_sigma
        """
        if len(self._values) < 5:
            return "normal"

        current_std = self.get_std()

        if current_std > 2.0 * self._historical_sigma:
            return "critical"
        elif current_std > 1.5 * self._historical_sigma:
            return "high"
        return "normal"

    def should_reduce_kelly(self) -> bool:
        """Return True if variance is high or critical."""
        return self.get_status() in ("high", "critical")

    def set_historical_sigma(self, sigma: float) -> None:
        """Set the baseline historical sigma for comparison."""
        if sigma > 0:
            self._historical_sigma = sigma
