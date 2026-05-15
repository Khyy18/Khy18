"""Эксплуатация бонусов на экспрессы (аккумуляторы).

Стратегия: собрать экспресс для получения бонуса (5-20% на выигрыш),
захеджировать каждую ногу через lay на бирже.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AccumulatorOpportunity:
    """Возможность для эксплуатации бонуса на экспресс."""

    legs: list[dict[str, Any]]
    combo_odds: float
    bonus_pct: float
    bonus_amount: float
    total_lay_cost: float
    net_profit: float


class AccumulatorExploit:
    """Эксплуатация бонусов букмекеров на аккумуляторы (5-20% бонус на комбо-выигрыш)."""

    def find_accumulator_opportunities(
        self, events: list[dict[str, Any]], min_legs: int = 3
    ) -> list[AccumulatorOpportunity]:
        """Найти оптимальные комбинации для эксплуатации бонуса на экспресс.

        Ищет события с минимальным спредом back/lay для формирования ног экспресса.
        """
        exchange_keys = {"betfair", "betfair_ex_uk", "smarkets", "matchbook"}
        legs_pool: list[dict[str, Any]] = []

        for event in events:
            home = event.get("home_team", "")
            away = event.get("away_team", "")
            event_name = f"{home} vs {away}"
            bookmakers = event.get("bookmakers", [])

            best_back: dict[str, dict[str, Any]] = {}
            best_lay: dict[str, float] = {}

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
                            if name not in best_lay or price < best_lay[name]:
                                best_lay[name] = price
                        else:
                            if name not in best_back or price > best_back[name]["back_odds"]:
                                best_back[name] = {
                                    "back_odds": price,
                                    "bookmaker": bk_key,
                                }

            # Находим лучшую ногу с минимальным спредом
            for name, back_info in best_back.items():
                if name in best_lay:
                    lay_odds = best_lay[name]
                    back_odds = back_info["back_odds"]
                    spread = lay_odds - back_odds
                    if spread >= 0 and back_odds >= 1.5:
                        legs_pool.append({
                            "event_name": event_name,
                            "outcome": name,
                            "back_odds": back_odds,
                            "lay_odds": lay_odds,
                            "bookmaker": back_info["bookmaker"],
                            "spread": spread,
                        })

        # Сортируем по спреду (минимальный лучше)
        legs_pool.sort(key=lambda x: x["spread"])

        opportunities: list[AccumulatorOpportunity] = []

        if len(legs_pool) >= min_legs:
            # Берем лучшие min_legs ног
            selected_legs = legs_pool[:min_legs]
            for bonus_pct in [0.05, 0.10, 0.15, 0.20]:
                result = self.calculate_acca_profit(selected_legs, bonus_pct, 100.0)
                if result["net_profit"] > 0:
                    opp = AccumulatorOpportunity(
                        legs=selected_legs,
                        combo_odds=result["combo_odds"],
                        bonus_pct=bonus_pct,
                        bonus_amount=result["bonus_amount"],
                        total_lay_cost=result["total_lay_cost"],
                        net_profit=result["net_profit"],
                    )
                    opportunities.append(opp)
                    logger.info(
                        "[ACCA] Найдена возможность: %d ног, бонус %.0f%%, прибыль %.2f",
                        min_legs,
                        bonus_pct * 100,
                        result["net_profit"],
                    )

        return opportunities

    def calculate_acca_profit(
        self, legs: list[dict[str, Any]], bonus_pct: float, stake: float
    ) -> dict[str, Any]:
        """Рассчитать прибыль с бонусом и lay-хеджированием.

        Каждая нога: {back_odds, lay_odds} (опционально lay_commission=0.05)

        combo_odds = произведение всех back_odds
        bonus_amount = combo_odds * stake * bonus_pct
        Для каждой ноги lay для гарантии:
          lay_stake_i = stake * product_other_back / (lay_odds_i - commission)
        total_lay_cost = сумма(lay_stake * (lay_odds - 1)) с учетом проигрышей

        Упрощенно: net_profit = bonus_amount - qualifying_loss
        qualifying_loss = stake * (1 - 1/combo_overround)

        Возвращает: {combo_odds, bonus_amount, lay_cost_per_leg, total_lay_cost, net_profit, roi_pct}
        """
        if not legs or stake <= 0:
            return {
                "combo_odds": 0.0,
                "bonus_amount": 0.0,
                "lay_cost_per_leg": [],
                "total_lay_cost": 0.0,
                "net_profit": 0.0,
                "roi_pct": 0.0,
            }

        combo_odds = 1.0
        for leg in legs:
            combo_odds *= leg.get("back_odds", 1.0)

        bonus_amount = combo_odds * stake * bonus_pct

        # Рассчитываем lay-стоимость для каждой ноги
        lay_cost_per_leg: list[float] = []
        total_lay_cost = 0.0

        for i, leg in enumerate(legs):
            back_odds = leg.get("back_odds", 1.0)
            lay_odds = leg.get("lay_odds", back_odds)
            commission = leg.get("lay_commission", 0.05)

            # Произведение back_odds остальных ног
            other_product = combo_odds / back_odds if back_odds > 0 else 1.0

            # Lay-ставка для хеджирования этой ноги
            denominator = lay_odds - commission
            if denominator <= 0:
                lay_stake_i = 0.0
            else:
                lay_stake_i = stake * other_product / denominator

            # Стоимость lay (потенциальный убыток если back выиграет)
            lay_liability = lay_stake_i * (lay_odds - 1.0)
            lay_cost_per_leg.append(round(lay_liability, 4))
            total_lay_cost += lay_liability

        # Qualifying loss - убыток от хеджирования без бонуса
        # Упрощенная формула: если все back выиграли, мы получаем combo_odds * stake
        # но платим lay на всех ногах
        qualifying_loss = total_lay_cost - stake * (combo_odds - 1.0)

        net_profit = bonus_amount - max(qualifying_loss, 0.0)
        roi_pct = (net_profit / stake * 100.0) if stake > 0 else 0.0

        return {
            "combo_odds": round(combo_odds, 4),
            "bonus_amount": round(bonus_amount, 4),
            "lay_cost_per_leg": lay_cost_per_leg,
            "total_lay_cost": round(total_lay_cost, 4),
            "net_profit": round(net_profit, 4),
            "roi_pct": round(roi_pct, 4),
        }
