"""Ядро поиска арбитражных возможностей.

ArbitrageScanner анализирует коэффициенты букмекеров и находит:
  - Surebets (гарантированную прибыль при ставках на все исходы)
  - Value bets (ставки с положительным математическим ожиданием)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import product
from typing import Any, Optional

from arbitrage import config

logger = logging.getLogger(__name__)


@dataclass
class ArbOpportunity:
    """Арбитражная возможность (surebet или value bet)."""

    type: str                     # "surebet" или "value_bet"
    sport: str                    # вид спорта
    event_name: str               # название события
    home: str                     # домашняя команда
    away: str                     # гостевая команда
    bookmakers: list[str]         # букмекеры, участвующие в арбитраже
    odds: list[float]             # коэффициенты
    profit_pct: float = 0.0       # процент прибыли (для surebets)
    edge_pct: float = 0.0         # процент edge (для value bets)
    timestamp: str = ""           # время обнаружения (ISO format)
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class ArbitrageScanner:
    """Сканер арбитражных возможностей."""

    def __init__(
        self,
        min_arb_profit: float = config.MIN_ARB_PROFIT,
        min_value_edge: float = config.MIN_VALUE_EDGE,
    ) -> None:
        self._min_arb_profit: float = min_arb_profit
        self._min_value_edge: float = min_value_edge

    def find_surebets(self, events: list[dict[str, Any]]) -> list[ArbOpportunity]:
        """Ищет surebets среди событий.

        Для каждого события проверяет все комбинации исходов
        у разных букмекеров. Если сумма обратных коэффициентов < 1,
        это гарантированная прибыль.

        Args:
            events: нормализованные события из OddsAPI

        Returns:
            Список найденных ArbOpportunity с type="surebet"
        """
        opportunities: list[ArbOpportunity] = []

        for event in events:
            sport: str = event.get("sport", "")
            home: str = event.get("home_team", "")
            away: str = event.get("away_team", "")
            event_name: str = f"{home} vs {away}"

            # Собираем лучшие коэффициенты по каждому исходу (h2h)
            h2h_data = self._extract_h2h_outcomes(event)
            if not h2h_data:
                continue

            # h2h_data: {outcome_name: [(odds, bookmaker), ...]}
            outcome_names = list(h2h_data.keys())
            if len(outcome_names) < 2:
                continue

            # Для каждого исхода берём лучший (максимальный) коэффициент
            best_odds: list[float] = []
            best_bookmakers: list[str] = []

            for outcome in outcome_names:
                if not h2h_data[outcome]:
                    break
                # Сортируем по коэффициенту (убывание)
                sorted_offers = sorted(h2h_data[outcome], key=lambda x: x[0], reverse=True)
                best_odds.append(sorted_offers[0][0])
                best_bookmakers.append(sorted_offers[0][1])

            if len(best_odds) != len(outcome_names):
                continue

            # Проверяем условие арбитража: sum(1/odds) < 1
            inverse_sum: float = sum(1.0 / o for o in best_odds if o > 0)

            if inverse_sum < 1.0:
                profit_pct: float = (1.0 / inverse_sum - 1.0) * 100.0

                if profit_pct >= self._min_arb_profit:
                    opp = ArbOpportunity(
                        type="surebet",
                        sport=sport,
                        event_name=event_name,
                        home=home,
                        away=away,
                        bookmakers=best_bookmakers,
                        odds=best_odds,
                        profit_pct=profit_pct,
                        details={
                            "outcomes": outcome_names,
                            "inverse_sum": inverse_sum,
                        },
                    )
                    opportunities.append(opp)
                    logger.info(
                        "Surebet найден: %s | прибыль %.2f%% | %s",
                        event_name, profit_pct, best_bookmakers,
                    )

        return opportunities

    def find_value_bets(
        self,
        events: list[dict[str, Any]],
        sharp_probs: dict[str, list[float]],
    ) -> list[ArbOpportunity]:
        """Ищет value bets - ставки с положительным edge.

        Сравнивает коэффициенты мягких букмекеров с true probability
        от sharp-букмекера (Pinnacle).

        Args:
            events: нормализованные события из OddsAPI
            sharp_probs: словарь {event_id: [fair_prob_1, fair_prob_2, ...]}

        Returns:
            Список ArbOpportunity с type="value_bet"
        """
        opportunities: list[ArbOpportunity] = []

        for event in events:
            event_id: str = event.get("id", "")
            if event_id not in sharp_probs:
                continue

            sport: str = event.get("sport", "")
            home: str = event.get("home_team", "")
            away: str = event.get("away_team", "")
            event_name: str = f"{home} vs {away}"
            fair_probs: list[float] = sharp_probs[event_id]

            for bm in event.get("bookmakers", []):
                bm_key: str = bm.get("key", "")
                # Пропускаем sharp-букмекеров (они сами - эталон)
                if bm_key.lower() == "pinnacle":
                    continue

                for market in bm.get("markets", []):
                    if market.get("key") != "h2h":
                        continue

                    outcomes = market.get("outcomes", [])
                    if len(outcomes) != len(fair_probs):
                        continue

                    for i, outcome in enumerate(outcomes):
                        odds: float = outcome.get("price", 0.0)
                        if odds <= 1.0:
                            continue

                        bk_prob: float = 1.0 / odds
                        sharp_prob: float = fair_probs[i]

                        if sharp_prob <= 0:
                            continue

                        # Edge = (bk_odds * sharp_prob - 1) * 100
                        # Если bk_prob < sharp_prob, значит букмекер
                        # недооценивает исход - это value
                        implied_value: float = odds * sharp_prob
                        edge: float = (implied_value - 1.0) * 100.0

                        if edge >= self._min_value_edge:
                            opp = ArbOpportunity(
                                type="value_bet",
                                sport=sport,
                                event_name=event_name,
                                home=home,
                                away=away,
                                bookmakers=[bm_key],
                                odds=[odds],
                                edge_pct=edge,
                                details={
                                    "outcome": outcome.get("name", ""),
                                    "bookmaker_prob": round(bk_prob, 4),
                                    "sharp_prob": round(sharp_prob, 4),
                                    "implied_value": round(implied_value, 4),
                                },
                            )
                            opportunities.append(opp)
                            logger.info(
                                "Value bet: %s | %s @ %.2f | edge %.2f%% | %s",
                                event_name,
                                outcome.get("name", ""),
                                odds,
                                edge,
                                bm_key,
                            )

        return opportunities

    @staticmethod
    def _extract_h2h_outcomes(
        event: dict[str, Any],
    ) -> dict[str, list[tuple[float, str]]]:
        """Извлекает h2h-исходы из всех букмекеров события.

        Returns:
            {outcome_name: [(odds, bookmaker_key), ...]}
        """
        outcomes_map: dict[str, list[tuple[float, str]]] = {}

        for bm in event.get("bookmakers", []):
            bm_key: str = bm.get("key", "")
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    name: str = outcome.get("name", "")
                    price: float = outcome.get("price", 0.0)
                    if name and price > 1.0:
                        if name not in outcomes_map:
                            outcomes_map[name] = []
                        outcomes_map[name].append((price, bm_key))

        return outcomes_map
