"""Монте-Карло симулятор P&L.

Прогнозирует финансовые результаты бота на основе исторических данных.
Чистый Python (random module), без numpy.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    """Результат Monte Carlo симуляции."""

    median_pnl: float
    mean_pnl: float
    p5_pnl: float  # 5th percentile
    p25_pnl: float  # 25th percentile
    p75_pnl: float  # 75th percentile
    p95_pnl: float  # 95th percentile
    prob_ruin: float  # probability bankroll drops below 10% of initial
    max_drawdown_pct: float  # worst-case drawdown
    expected_roi_pct: float
    scenarios_count: int


class MonteCarloSimulator:
    """Симуляция P&L на N сценариев."""

    def __init__(
        self,
        win_rate: float = 0.55,
        avg_profit_pct: float = 2.5,
        avg_loss_pct: float = 1.0,
        bets_per_day: int = 5,
    ) -> None:
        self._win_rate = win_rate
        self._avg_profit_pct = avg_profit_pct
        self._avg_loss_pct = avg_loss_pct
        self._bets_per_day = bets_per_day

    def simulate(
        self, bankroll: float, days: int = 30, scenarios: int = 10000
    ) -> SimulationResult:
        """Run Monte Carlo simulation.

        For each scenario:
        1. Start with bankroll
        2. For each day, simulate bets_per_day bets
        3. Each bet: random() < win_rate => profit, else loss
        4. Track final bankrolls, max drawdowns

        Returns SimulationResult with percentiles and risk metrics.
        """
        final_bankrolls: list[float] = []
        max_drawdowns: list[float] = []
        ruin_count = 0
        ruin_threshold = bankroll * 0.1

        for _ in range(scenarios):
            current = bankroll
            hwm = bankroll
            worst_dd = 0.0

            for _day in range(days):
                for _bet in range(self._bets_per_day):
                    if random.random() < self._win_rate:
                        current += current * (self._avg_profit_pct / 100.0)
                    else:
                        current -= current * (self._avg_loss_pct / 100.0)

                    if current > hwm:
                        hwm = current
                    dd = (hwm - current) / hwm * 100.0 if hwm > 0 else 0.0
                    worst_dd = max(worst_dd, dd)

                    if current < ruin_threshold:
                        ruin_count += 1
                        break  # This scenario is ruined
                else:
                    continue
                break  # Break outer loop too

            final_bankrolls.append(current)
            max_drawdowns.append(worst_dd)

        # Calculate percentiles
        final_bankrolls.sort()
        pnls = [fb - bankroll for fb in final_bankrolls]
        pnls.sort()

        def percentile(sorted_list: list[float], p: float) -> float:
            idx = int(p / 100.0 * (len(sorted_list) - 1))
            return sorted_list[idx]

        median_pnl = percentile(pnls, 50.0)
        mean_pnl = sum(pnls) / len(pnls) if pnls else 0.0

        return SimulationResult(
            median_pnl=round(median_pnl, 2),
            mean_pnl=round(mean_pnl, 2),
            p5_pnl=round(percentile(pnls, 5.0), 2),
            p25_pnl=round(percentile(pnls, 25.0), 2),
            p75_pnl=round(percentile(pnls, 75.0), 2),
            p95_pnl=round(percentile(pnls, 95.0), 2),
            prob_ruin=round(ruin_count / scenarios, 4),
            max_drawdown_pct=round(max(max_drawdowns) if max_drawdowns else 0.0, 2),
            expected_roi_pct=round(mean_pnl / bankroll * 100.0 if bankroll > 0 else 0.0, 2),
            scenarios_count=scenarios,
        )

    def estimate_kelly_reduction(self, current_drawdown_pct: float) -> float:
        """Recommend Kelly reduction based on drawdown.

        factor = 1.0 - (drawdown_pct / 15.0)^2
        Clamp to [0.0, 1.0]
        """
        max_dd = 15.0
        if current_drawdown_pct <= 0:
            return 1.0
        if current_drawdown_pct >= max_dd:
            return 0.0
        factor = 1.0 - (current_drawdown_pct / max_dd) ** 2
        return round(max(0.0, min(1.0, factor)), 4)
