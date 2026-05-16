"""In-Play Cash-Out Engine - поиск возможностей для кэшаута ставок.

Сравнивает текущие коэффициенты с pre-match ставками и определяет,
когда выгодно зафиксировать прибыль через обратную ставку (lay).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from arbitrage import config

logger = logging.getLogger(__name__)


@dataclass
class CashoutOpportunity:
    """Возможность для кэшаута (фиксации прибыли/убытка)."""

    event_name: str                # название события
    sport: str                     # вид спорта
    home: str                      # домашняя команда
    away: str                      # гостевая команда
    original_bet: dict[str, Any]   # {bookmaker, outcome, odds, stake, placed_ts}
    current_odds: float            # текущий коэффициент на тот же исход
    cashout_profit_pct: float      # прибыль от кэшаута (%)
    recommendation: str            # рекомендация: "cashout" / "hold" / "partial_cashout"
    timestamp: str = ""            # время обнаружения (ISO format)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class CashoutEngine:
    """Движок поиска и расчёта кэшаут-возможностей."""

    def find_cashout_opportunities(
        self,
        pre_match_bets: list[dict[str, Any]],
        current_events: list[dict[str, Any]],
    ) -> list[CashoutOpportunity]:
        """Находит возможности для кэшаута pre-match ставок.

        Сопоставляет pre-match ставки с текущими событиями по event_id/name,
        проверяет, делают ли текущие коэффициенты кэшаут прибыльным.

        Args:
            pre_match_bets: список pre-match ставок, каждая содержит:
                {event_id, event_name, bookmaker, outcome, odds, stake, placed_ts}
            current_events: текущие нормализованные события из OddsAPI

        Returns:
            Список CashoutOpportunity
        """
        opportunities: list[CashoutOpportunity] = []

        # Строим индекс текущих коэффициентов по event_id
        current_odds_map: dict[str, dict[str, float]] = {}
        event_info_map: dict[str, dict[str, str]] = {}

        for event in current_events:
            event_id: str = event.get("id", "")
            if not event_id:
                continue

            sport: str = event.get("sport", "")
            home: str = event.get("home_team", "")
            away: str = event.get("away_team", "")
            event_info_map[event_id] = {
                "sport": sport,
                "home": home,
                "away": away,
                "event_name": f"{home} vs {away}",
            }

            for bm in event.get("bookmakers", []):
                for market in bm.get("markets", []):
                    if market.get("key") != "h2h":
                        continue
                    for outcome in market.get("outcomes", []):
                        name: str = outcome.get("name", "")
                        price: float = outcome.get("price", 0.0)
                        if name and price > 1.0:
                            key = f"{event_id}::{name}"
                            # Берём лучший (наименьший) текущий коэффициент для lay
                            if key not in current_odds_map:
                                current_odds_map[key] = {}
                            bm_key: str = bm.get("key", "")
                            current_odds_map[key][bm_key] = price

        # Проверяем каждую pre-match ставку
        for bet in pre_match_bets:
            event_id = bet.get("event_id", "")
            outcome_name: str = bet.get("outcome", "")
            original_odds: float = bet.get("odds", 0.0)
            stake: float = bet.get("stake", 0.0)

            if not event_id or not outcome_name or original_odds <= 1.0 or stake <= 0:
                continue

            key = f"{event_id}::{outcome_name}"
            bm_odds = current_odds_map.get(key, {})

            if not bm_odds:
                continue

            # Берём лучший (наименьший) текущий коэффициент для расчёта кэшаута
            best_current_odds = min(bm_odds.values())

            # Profit = (original_odds / current_odds - 1) * 100
            cashout_profit_pct = (original_odds / best_current_odds - 1.0) * 100.0

            # Рекомендация
            if cashout_profit_pct > 10.0:
                recommendation = "cashout"
            elif cashout_profit_pct > 3.0:
                recommendation = "partial_cashout"
            else:
                recommendation = "hold"

            # Информация о событии
            info = event_info_map.get(event_id, {})
            event_name = info.get("event_name", bet.get("event_name", "Unknown"))
            sport = info.get("sport", bet.get("sport", ""))
            home = info.get("home", "")
            away = info.get("away", "")

            opp = CashoutOpportunity(
                event_name=event_name,
                sport=sport,
                home=home,
                away=away,
                original_bet={
                    "bookmaker": bet.get("bookmaker", ""),
                    "outcome": outcome_name,
                    "odds": original_odds,
                    "stake": stake,
                    "placed_ts": bet.get("placed_ts", ""),
                },
                current_odds=best_current_odds,
                cashout_profit_pct=round(cashout_profit_pct, 2),
                recommendation=recommendation,
            )
            opportunities.append(opp)

            if config.DRY_RUN:
                logger.info(
                    "DRY_RUN cashout: %s | %s @ %.2f -> %.2f | profit %.2f%% | %s",
                    event_name, outcome_name, original_odds,
                    best_current_odds, cashout_profit_pct, recommendation,
                )

        return opportunities

    def calculate_cashout_profit(
        self,
        original_odds: float,
        current_odds: float,
        stake: float,
    ) -> float:
        """Рассчитывает гарантированную прибыль от кэшаута.

        Формула back-to-lay: profit = stake * (original_odds / current_odds - 1)
        Если текущие коэффициенты упали (исход более вероятен),
        можно зафиксировать прибыль.

        Args:
            original_odds: коэффициент в момент размещения ставки
            current_odds: текущий коэффициент
            stake: размер первоначальной ставки

        Returns:
            Гарантированная прибыль (может быть отрицательной)
        """
        if current_odds <= 1.0 or original_odds <= 1.0 or stake <= 0:
            return 0.0

        profit = stake * (original_odds / current_odds - 1.0)
        return round(profit, 2)
