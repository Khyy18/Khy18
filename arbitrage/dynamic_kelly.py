"""Динамический Kelly - автоматическое снижение ставок при убытках.

Fractional Kelly = base_kelly * reduction_factor
Фактор зависит от drawdown, losing streak и variance.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


class DynamicKelly:
    """Автоматическое снижение размера ставок при серии убытков."""

    def __init__(self, max_drawdown_pct: float = 15.0) -> None:
        self._max_drawdown_pct = max_drawdown_pct

    def get_reduction_factor(self, state: dict[str, Any]) -> float:
        """Get current Kelly reduction factor.

        state keys:
          - hwm: high water mark (peak bankroll)
          - current_bankroll: current bankroll
          - recent_pnls: list of last N PnL values
          - losing_streak: current consecutive losses count

        Formula:
          base_factor = 1.0 - (drawdown_pct / max_drawdown_pct)^2
          if losing_streak > 5: multiply by 0.7
          if variance > 2*historical_avg: multiply by 0.8
        Clamp to [0.0, 1.0]
        """
        hwm = float(state.get("hwm", 1000.0))
        current = float(state.get("current_bankroll", hwm))
        recent_pnls = state.get("recent_pnls", [])
        losing_streak = int(state.get("losing_streak", 0))

        # Calculate drawdown percentage
        if hwm <= 0:
            drawdown_pct = 0.0
        else:
            drawdown_pct = (hwm - current) / hwm * 100.0
            drawdown_pct = max(0.0, drawdown_pct)

        # Base factor from drawdown
        if drawdown_pct >= self._max_drawdown_pct:
            factor = 0.0
        else:
            factor = 1.0 - (drawdown_pct / self._max_drawdown_pct) ** 2

        # Losing streak penalty
        if losing_streak > 5:
            factor *= 0.7
            logger.info("[DYNAMIC_KELLY] Losing streak %d, фактор снижен на 30%%", losing_streak)

        # Variance penalty
        if recent_pnls and len(recent_pnls) >= 10:
            mean = sum(recent_pnls) / len(recent_pnls)
            variance = sum((x - mean) ** 2 for x in recent_pnls) / len(recent_pnls)
            # Historical average variance estimate (based on expected win/loss)
            historical_avg_var = (2.5**2 + 1.0**2) / 2.0  # simple estimate
            if variance > 2.0 * historical_avg_var:
                factor *= 0.8
                logger.info(
                    "[DYNAMIC_KELLY] Высокая дисперсия (%.2f > %.2f), фактор снижен на 20%%",
                    variance,
                    2.0 * historical_avg_var,
                )

        factor = max(0.0, min(1.0, factor))
        logger.debug("[DYNAMIC_KELLY] factor=%.3f (dd=%.1f%%, streak=%d)", factor, drawdown_pct, losing_streak)
        return round(factor, 4)
