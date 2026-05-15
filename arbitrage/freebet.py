"""Конвертер фрибетов - перевод фрибетов в реальные деньги через lay-биржу.

Стратегия: поставить фрибет на Back у мягкого букмекера,
захеджировать через Lay на бирже (Betfair).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class FreeBetConversion:
    """Результат конвертации фрибета."""

    event_name: str
    back_bookmaker: str
    lay_exchange: str
    back_odds: float
    lay_odds: float
    free_bet_amount: float
    lay_stake: float
    guaranteed_profit: float
    conversion_rate: float


class FreeBetConverter:
    """Конвертирует фрибеты в реальные деньги через lay на бирже."""

    def find_best_conversion(
        self, free_bet_amount: float, events: list[dict[str, Any]]
    ) -> Optional[FreeBetConversion]:
        """Найти лучшую пару back/lay для конвертации фрибета.

        Перебирает события, ищет лучшие back-коэффициенты у мягких букмекеров
        в паре с наименьшими lay-коэффициентами на бирже.
        """
        best: Optional[FreeBetConversion] = None
        best_rate = 0.0

        exchange_keys = {"betfair", "betfair_ex_uk", "smarkets", "matchbook"}

        for event in events:
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            event_name = f"{home} vs {away}"
            bookmakers = event.get("bookmakers", [])

            # Собираем lay-коэффициенты с бирж
            lay_odds_map: dict[str, float] = {}
            back_odds_map: dict[str, dict[str, float]] = {}

            for bk in bookmakers:
                bk_key = bk.get("key", "")
                for market in bk.get("markets", []):
                    if market.get("key") != "h2h":
                        continue
                    for outcome in market.get("outcomes", []):
                        name = outcome.get("name", "")
                        price = outcome.get("price", 0.0)
                        if price <= 1.0:
                            continue

                        if bk_key in exchange_keys:
                            # На бирже это lay-коэффициенты
                            if name not in lay_odds_map or price < lay_odds_map[name]:
                                lay_odds_map[name] = price
                        else:
                            # У обычного букмекера - back-коэффициенты
                            if bk_key not in back_odds_map:
                                back_odds_map[bk_key] = {}
                            if name not in back_odds_map[bk_key] or price > back_odds_map[bk_key][name]:
                                back_odds_map[bk_key][name] = price

            # Ищем лучшую пару
            for bk_key, odds_map in back_odds_map.items():
                for outcome_name, back_odds in odds_map.items():
                    if outcome_name not in lay_odds_map:
                        continue
                    lay_odds = lay_odds_map[outcome_name]

                    result = self.calculate_conversion(
                        free_bet_amount, back_odds, lay_odds
                    )
                    rate = result["conversion_rate"]

                    if rate > best_rate:
                        best_rate = rate
                        best = FreeBetConversion(
                            event_name=event_name,
                            back_bookmaker=bk_key,
                            lay_exchange="betfair",
                            back_odds=back_odds,
                            lay_odds=lay_odds,
                            free_bet_amount=free_bet_amount,
                            lay_stake=round(result["lay_stake"], 4),
                            guaranteed_profit=round(result["guaranteed_profit"], 4),
                            conversion_rate=round(rate, 4),
                        )

        if best:
            logger.info(
                "[FREEBET] Лучшая конвертация: %s, конверсия %.1f%%",
                best.event_name,
                best.conversion_rate,
            )

        return best

    def calculate_conversion(
        self,
        free_bet: float,
        back_odds: float,
        lay_odds: float,
        commission: float = 0.05,
    ) -> dict[str, Any]:
        """Рассчитать прибыль от конвертации фрибета.

        Для SNR (stake not returned) фрибетов:
        - lay_stake = (back_odds - 1) * free_bet / (lay_odds - commission)
        - profit_if_back_wins = (back_odds - 1) * free_bet - lay_stake * (lay_odds - 1)
        - profit_if_back_loses = lay_stake * (1 - commission)
        - Оптимально: уравнять оба исхода
        - guaranteed_profit = min(profit_if_back_wins, profit_if_back_loses)
        - conversion_rate = guaranteed_profit / free_bet * 100
        """
        if lay_odds <= 1.0 or back_odds <= 1.0:
            return {
                "lay_stake": 0.0,
                "profit_if_back_wins": 0.0,
                "profit_if_back_loses": 0.0,
                "guaranteed_profit": 0.0,
                "conversion_rate": 0.0,
            }

        # Формула для SNR фрибета с уравниванием прибыли
        lay_stake = (back_odds - 1.0) * free_bet / (lay_odds - commission)

        profit_if_back_wins = (back_odds - 1.0) * free_bet - lay_stake * (lay_odds - 1.0)
        profit_if_back_loses = lay_stake * (1.0 - commission)

        guaranteed_profit = min(profit_if_back_wins, profit_if_back_loses)
        conversion_rate = guaranteed_profit / free_bet * 100.0 if free_bet > 0 else 0.0

        return {
            "lay_stake": round(lay_stake, 4),
            "profit_if_back_wins": round(profit_if_back_wins, 4),
            "profit_if_back_loses": round(profit_if_back_loses, 4),
            "guaranteed_profit": round(guaranteed_profit, 4),
            "conversion_rate": round(conversion_rate, 4),
        }
