"""Стратегия Live Goal Arbitrage - ставка pre-match Over, cashout после первого гола.

Стратегия: поставить pre-match на Over 2.5 в лигах с высоким xG,
после первого гола коэффициент падает, фиксируем прибыль через cashout.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Ожидаемые голы за 35 минут по лигам
LEAGUE_XG_35MIN: dict[str, float] = {
    "soccer_epl": 0.65,
    "soccer_spain_la_liga": 0.60,
    "soccer_germany_bundesliga": 0.72,
    "soccer_italy_serie_a": 0.58,
    "soccer_france_ligue_one": 0.60,
    "soccer_uefa_champs_league": 0.67,
}


@dataclass
class LiveGoalOpportunity:
    """Возможность для стратегии live-гол."""

    event_name: str
    sport: str
    pre_match_over_odds: float
    expected_live_odds: float
    goal_probability: float
    expected_value: float
    profit_if_goal: float
    loss_if_no_goal: float


class LiveGoalArbitrage:
    """Стратегия: ставка pre-match Over, cashout после первого гола."""

    def find_goal_arb_candidates(
        self, events: list[dict[str, Any]]
    ) -> list[LiveGoalOpportunity]:
        """Найти матчи с высоким xG для стратегии live-гол.

        Фильтрует футбольные события, анализирует рынок Over 2.5,
        оценивает вероятность гола из LEAGUE_XG_35MIN.
        """
        opportunities: list[LiveGoalOpportunity] = []

        for event in events:
            sport = event.get("sport", "")
            if sport not in LEAGUE_XG_35MIN:
                continue

            home = event.get("home_team", "")
            away = event.get("away_team", "")
            event_name = f"{home} vs {away}"
            xg_35 = LEAGUE_XG_35MIN[sport]

            # Вероятность хотя бы одного гола за 35 минут (Пуассон)
            # P(>=1 goal) = 1 - e^(-xg_35) ~ xg_35 для малых значений
            # Используем приближение: 1 - e^(-lambda)
            import math
            goal_probability = 1.0 - math.exp(-xg_35)

            # Ищем рынок Over 2.5 (или h2h как прокси)
            for bk in event.get("bookmakers", []):
                for market in bk.get("markets", []):
                    market_key = market.get("key", "")
                    # Проверяем totals рынок или используем h2h odds как прокси
                    if market_key == "totals":
                        for outcome in market.get("outcomes", []):
                            if outcome.get("name") == "Over" and outcome.get("point", 0) == 2.5:
                                pre_match_odds = outcome.get("price", 0.0)
                                if pre_match_odds <= 1.0:
                                    continue
                                # После гола коэффициент Over 2.5 обычно падает до ~1.3-1.5
                                expected_live_odds = 1.4
                                result = self.calculate_expected_profit(
                                    pre_match_odds, expected_live_odds, goal_probability
                                )
                                if result["expected_value"] > 0:
                                    opp = LiveGoalOpportunity(
                                        event_name=event_name,
                                        sport=sport,
                                        pre_match_over_odds=pre_match_odds,
                                        expected_live_odds=expected_live_odds,
                                        goal_probability=round(goal_probability, 4),
                                        expected_value=result["expected_value"],
                                        profit_if_goal=result["profit_if_goal"],
                                        loss_if_no_goal=result["loss_if_no_goal"],
                                    )
                                    opportunities.append(opp)
                                    logger.info(
                                        "[LIVE_GOAL] Кандидат: %s, EV=%.2f%%",
                                        event_name,
                                        result["expected_value"],
                                    )
                    elif market_key == "h2h" and not any(
                        m.get("key") == "totals" for m in bk.get("markets", [])
                    ):
                        # Используем h2h как прокси - берем средний коэффициент
                        outcomes = market.get("outcomes", [])
                        if not outcomes:
                            continue
                        avg_odds = sum(o.get("price", 0) for o in outcomes) / len(outcomes)
                        if avg_odds <= 1.5:
                            continue
                        # Оценка Over 2.5 odds из средних h2h
                        pre_match_odds = avg_odds * 0.85
                        if pre_match_odds <= 1.0:
                            continue
                        expected_live_odds = 1.4
                        result = self.calculate_expected_profit(
                            pre_match_odds, expected_live_odds, goal_probability
                        )
                        if result["expected_value"] > 0:
                            opp = LiveGoalOpportunity(
                                event_name=event_name,
                                sport=sport,
                                pre_match_over_odds=round(pre_match_odds, 4),
                                expected_live_odds=expected_live_odds,
                                goal_probability=round(goal_probability, 4),
                                expected_value=result["expected_value"],
                                profit_if_goal=result["profit_if_goal"],
                                loss_if_no_goal=result["loss_if_no_goal"],
                            )
                            opportunities.append(opp)

        return opportunities

    def calculate_expected_profit(
        self,
        pre_match_odds: float,
        expected_live_odds: float,
        goal_probability: float,
    ) -> dict[str, Any]:
        """Рассчитать математическое ожидание прибыли.

        EV = prob_goal * profit_if_goal + (1-prob_goal) * loss_if_no_goal

        profit_if_goal = stake * (pre_match_odds/expected_live_odds - 1)
          (cashout value = stake * pre_match_odds / expected_live_odds)
        loss_if_no_goal = stake * (pre_match_odds/no_goal_odds - 1)
          Если нет гола к 35 мин, Over 2.5 odds растут (примерно x1.5 от pre_match),
          cashout дает частичный возврат.

        Возвращает: {ev, profit_if_goal, loss_if_no_goal, expected_value, roi_pct}
        """
        stake = 100.0  # нормализуем к 100

        if expected_live_odds <= 0 or pre_match_odds <= 0:
            return {
                "ev": 0.0,
                "profit_if_goal": 0.0,
                "loss_if_no_goal": 0.0,
                "expected_value": 0.0,
                "roi_pct": 0.0,
            }

        # Cashout value после гола (odds падают)
        cashout_value_goal = stake * pre_match_odds / expected_live_odds
        profit_if_goal = cashout_value_goal - stake

        # Если нет гола, odds Over 2.5 растут; cashout при повышенных odds
        # Без гола к 35-й минуте odds увеличиваются примерно на 30-50%
        no_goal_odds_factor = 1.3  # odds увеличиваются на 30%
        no_goal_live_odds = pre_match_odds * no_goal_odds_factor
        cashout_value_no_goal = stake * pre_match_odds / no_goal_live_odds
        loss_if_no_goal = cashout_value_no_goal - stake  # отрицательное значение (убыток)

        # Математическое ожидание
        ev = goal_probability * profit_if_goal + (1.0 - goal_probability) * loss_if_no_goal
        roi_pct = ev / stake * 100.0

        return {
            "ev": round(ev, 4),
            "profit_if_goal": round(profit_if_goal, 4),
            "loss_if_no_goal": round(loss_if_no_goal, 4),
            "expected_value": round(roi_pct, 4),
            "roi_pct": round(roi_pct, 4),
        }
