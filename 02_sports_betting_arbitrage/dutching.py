"""Датчинг (Dutching) - распределение ставок на несколько исходов у одного букмекера.

Стратегия: найти букмекера с overround < max_overround и распределить ставки так,
чтобы гарантировать равную прибыль на любой исход.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DutchingOpportunity:
    """Возможность для датчинга."""

    event_name: str
    sport: str
    bookmaker: str
    odds: list[float]
    stakes: list[float]
    guaranteed_return: float
    profit_pct: float


class DutchingEngine:
    """Датчинг: ставки на несколько исходов у ОДНОГО букмекера с гарантированной прибылью."""

    def __init__(self, max_overround: float = 0.02) -> None:
        self._max_overround = max_overround

    def find_dutching_opportunities(
        self, events: list[dict[str, Any]]
    ) -> list[DutchingOpportunity]:
        """Найти события где один букмекер имеет overround < max_overround (2%).

        Сканирует каждый рынок h2h букмекера, вычисляет sum(1/oi),
        если < 1 + max_overround - это возможность для датчинга.
        """
        opportunities: list[DutchingOpportunity] = []

        for event in events:
            sport = event.get("sport", "")
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            event_name = f"{home} vs {away}"

            for bk in event.get("bookmakers", []):
                bk_key = bk.get("key", "")
                for market in bk.get("markets", []):
                    if market.get("key") != "h2h":
                        continue
                    outcomes = market.get("outcomes", [])
                    if len(outcomes) < 2:
                        continue

                    odds = [o["price"] for o in outcomes]
                    if any(od <= 1.0 for od in odds):
                        continue

                    inverse_sum = sum(1.0 / od for od in odds)

                    # overround = inverse_sum - 1.0
                    # Датчинг выгоден когда overround < max_overround
                    if inverse_sum < 1.0 + self._max_overround:
                        total_stake = 100.0
                        stakes = self.calculate_dutch_stakes(odds, total_stake)
                        guaranteed_return = total_stake / inverse_sum
                        profit_pct = (guaranteed_return / total_stake - 1.0) * 100.0

                        opp = DutchingOpportunity(
                            event_name=event_name,
                            sport=sport,
                            bookmaker=bk_key,
                            odds=odds,
                            stakes=stakes,
                            guaranteed_return=round(guaranteed_return, 4),
                            profit_pct=round(profit_pct, 4),
                        )
                        opportunities.append(opp)
                        logger.info(
                            "[DUTCHING] Найдена возможность: %s @ %s, прибыль %.2f%%",
                            event_name,
                            bk_key,
                            profit_pct,
                        )

        return opportunities

    def calculate_dutch_stakes(
        self, odds: list[float], total_stake: float
    ) -> list[float]:
        """Рассчитать оптимальные ставки для датчинга.

        Формула: stake_i = total_stake * (1/oi) / sum(1/oj)
        Возврат при любом исходе = total_stake / sum(1/oj) (одинаков для всех).
        """
        if not odds or any(od <= 0 for od in odds):
            return []

        inverse_sum = sum(1.0 / od for od in odds)
        if inverse_sum == 0:
            return []

        stakes = [
            round(total_stake * (1.0 / od) / inverse_sum, 4) for od in odds
        ]
        return stakes
