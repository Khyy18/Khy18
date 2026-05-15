"""Поиск Middle-возможностей (коридоров) на рынках тоталов и спредов.

Находит ситуации, когда разные букмекеры предлагают линии,
создающие коридор (middle), в который может попасть результат.
"""

from __future__ import annotations

import logging
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from arbitrage.ai_rate_limiter import AiRateLimiter

_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)
try:
    import ai_router
except ImportError:
    ai_router = None  # type: ignore

logger = logging.getLogger(__name__)

# Общий rate limiter для AI-запросов
_rate_limiter = AiRateLimiter()


def poisson_pmf(k: int, lam: float) -> float:
    """Вероятность P(X = k) для распределения Пуассона. Без scipy."""
    if k < 0 or lam <= 0:
        return 0.0
    return (lam ** k) * math.exp(-lam) / math.factorial(k)


LEAGUE_AVERAGES: dict[str, float] = {
    "soccer_epl": 2.7,
    "soccer_spain_la_liga": 2.5,
    "soccer_germany_bundesliga": 3.0,
    "soccer_italy_serie_a": 2.4,
    "soccer_france_ligue_one": 2.5,
    "soccer_uefa_champs_league": 2.8,
    "basketball_nba": 220.5,
    "basketball_euroleague": 155.0,
}


def _norm_cdf(x: float) -> float:
    """Approximate CDF of standard normal distribution. No scipy."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def compute_poisson_probability(corridor_low: float, corridor_high: float, sport: str) -> float:
    """Вычислить вероятность попадания результата в коридор [low, high].

    Для футбола: используем Poisson distribution (суммируем P(k) для целых k в коридоре).
    Для баскетбола: нормальное приближение (std ~ 10% от среднего).
    Для неизвестных спортов: наивная формула (corridor_width / corridor_high).
    """
    lam = LEAGUE_AVERAGES.get(sport)
    if lam is None:
        # Fallback - naive
        width = corridor_high - corridor_low
        return width / corridor_high if corridor_high > 0 else 0.0

    if sport.startswith("basketball"):
        # Normal approximation for basketball (high-scoring)
        mean = lam
        std = mean * 0.1  # ~10% standard deviation
        # P(low < X < high) using error function approximation
        z_low = (corridor_low - mean) / std if std > 0 else 0
        z_high = (corridor_high - mean) / std if std > 0 else 0
        prob = (_norm_cdf(z_high) - _norm_cdf(z_low))
        return max(0.0, min(1.0, prob))
    else:
        # Poisson for soccer/football (low-scoring)
        total_prob = 0.0
        # Sum P(k) for integer k strictly inside corridor
        k_start = int(math.floor(corridor_low)) + 1 if corridor_low == int(corridor_low) else int(math.ceil(corridor_low))
        k_end = int(math.ceil(corridor_high)) - 1 if corridor_high == int(corridor_high) else int(math.floor(corridor_high))
        for k in range(k_start, k_end + 1):
            total_prob += poisson_pmf(k, lam)
        return max(0.0, min(1.0, total_prob))


@dataclass
class MiddleOpportunity:
    """Возможность middle (коридор) между линиями разных букмекеров."""

    type: str                         # "middle_totals" / "middle_spreads" / "middle_asian"
    sport: str                        # вид спорта
    event_name: str                   # название события
    home: str                         # домашняя команда
    away: str                         # гостевая команда
    leg1: dict[str, Any]              # {bookmaker, market, line, odds, outcome}
    leg2: dict[str, Any]              # {bookmaker, market, line, odds, outcome}
    middle_range: list[float]         # [нижняя граница, верхняя граница]
    middle_probability: float = 0.0   # вероятность попадания в коридор
    worst_case_loss_pct: float = 0.0  # потери в худшем случае (%)
    best_case_profit_pct: float = 0.0 # прибыль в лучшем случае (%)
    expected_value_pct: float = 0.0   # математическое ожидание (%)
    timestamp: str = ""               # время обнаружения (ISO format)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class MiddleScanner:
    """Сканер middle-возможностей (коридоров) на рынках тоталов и спредов."""

    def find_middles_totals(self, events: list[dict[str, Any]]) -> list[MiddleOpportunity]:
        """Ищет middle-возможности на рынке тоталов.

        Для каждого события собирает все линии тоталов от всех букмекеров.
        Находит пары, где Over X у одного букмекера и Under Y у другого,
        при условии X < Y (есть коридор между X и Y).

        Args:
            events: нормализованные события из OddsAPI

        Returns:
            Список MiddleOpportunity с type="middle_totals"
        """
        opportunities: list[MiddleOpportunity] = []

        for event in events:
            sport: str = event.get("sport", "")
            home: str = event.get("home_team", "")
            away: str = event.get("away_team", "")
            event_name: str = f"{home} vs {away}"

            # Собираем все Over и Under линии с их коэффициентами
            overs: list[dict[str, Any]] = []   # [{bookmaker, line, odds}]
            unders: list[dict[str, Any]] = []  # [{bookmaker, line, odds}]

            for bm in event.get("bookmakers", []):
                bm_key: str = bm.get("key", "")
                for market in bm.get("markets", []):
                    if market.get("key") != "totals":
                        continue
                    for outcome in market.get("outcomes", []):
                        name: str = outcome.get("name", "")
                        price: float = outcome.get("price", 0.0)
                        point: Optional[float] = outcome.get("point")
                        if price <= 1.0 or point is None:
                            continue
                        if name == "Over":
                            overs.append({"bookmaker": bm_key, "line": point, "odds": price})
                        elif name == "Under":
                            unders.append({"bookmaker": bm_key, "line": point, "odds": price})

            # Ищем пары с коридором: Over X < Under Y
            for over in overs:
                for under in unders:
                    if over["bookmaker"] == under["bookmaker"]:
                        continue
                    if over["line"] < under["line"]:
                        # Коридор существует
                        corridor_low = over["line"]
                        corridor_high = under["line"]

                        # Расчет worst-case (обе ноги проигрывают)
                        stake_total = 2.0  # ставим 1 на каждую ногу
                        worst_case_loss = stake_total - 0.0  # теряем обе ставки
                        worst_case_loss_pct = -100.0  # теряем 100% от вложений

                        # Расчет best-case (обе ноги выигрывают)
                        payout_over = over["odds"]
                        payout_under = under["odds"]
                        best_case_profit = (payout_over + payout_under) - stake_total
                        best_case_profit_pct = (best_case_profit / stake_total) * 100.0

                        # Вероятность попадания в коридор
                        corridor_width = corridor_high - corridor_low
                        middle_probability = compute_poisson_probability(corridor_low, corridor_high, sport)

                        # EV = best_case_profit_pct * probability - 100 * (1 - probability)
                        expected_value_pct = (
                            best_case_profit_pct * middle_probability
                            + worst_case_loss_pct * (1.0 - middle_probability)
                        )

                        opp = MiddleOpportunity(
                            type="middle_totals",
                            sport=sport,
                            event_name=event_name,
                            home=home,
                            away=away,
                            leg1={
                                "bookmaker": over["bookmaker"],
                                "market": "totals",
                                "line": over["line"],
                                "odds": over["odds"],
                                "outcome": "Over",
                            },
                            leg2={
                                "bookmaker": under["bookmaker"],
                                "market": "totals",
                                "line": under["line"],
                                "odds": under["odds"],
                                "outcome": "Under",
                            },
                            middle_range=[corridor_low, corridor_high],
                            middle_probability=middle_probability,
                            worst_case_loss_pct=worst_case_loss_pct,
                            best_case_profit_pct=best_case_profit_pct,
                            expected_value_pct=expected_value_pct,
                        )
                        opportunities.append(opp)
                        logger.info(
                            "Middle (totals): %s | коридор [%.1f, %.1f] | EV %.2f%%",
                            event_name, corridor_low, corridor_high, expected_value_pct,
                        )

        return opportunities

    def find_middles_spreads(self, events: list[dict[str, Any]]) -> list[MiddleOpportunity]:
        """Ищет middle-возможности на рынке спредов.

        Для каждого события собирает все спреды от всех букмекеров.
        Находит пары, где Team A -X у bk1 и Team B +Y у bk2,
        при условии Y > X (есть коридор).

        Args:
            events: нормализованные события из OddsAPI

        Returns:
            Список MiddleOpportunity с type="middle_spreads"
        """
        opportunities: list[MiddleOpportunity] = []

        for event in events:
            sport: str = event.get("sport", "")
            home: str = event.get("home_team", "")
            away: str = event.get("away_team", "")
            event_name: str = f"{home} vs {away}"

            # Собираем все spread-линии: {team_name: [{bookmaker, line, odds}]}
            spreads_by_team: dict[str, list[dict[str, Any]]] = {}

            for bm in event.get("bookmakers", []):
                bm_key: str = bm.get("key", "")
                for market in bm.get("markets", []):
                    if market.get("key") != "spreads":
                        continue
                    for outcome in market.get("outcomes", []):
                        name: str = outcome.get("name", "")
                        price: float = outcome.get("price", 0.0)
                        point: Optional[float] = outcome.get("point")
                        if price <= 1.0 or point is None or not name:
                            continue
                        if name not in spreads_by_team:
                            spreads_by_team[name] = []
                        spreads_by_team[name].append({
                            "bookmaker": bm_key,
                            "line": point,
                            "odds": price,
                        })

            # Ищем коридоры между разными командами
            teams = list(spreads_by_team.keys())
            for i in range(len(teams)):
                for j in range(len(teams)):
                    if i == j:
                        continue
                    team_a = teams[i]
                    team_b = teams[j]

                    for spread_a in spreads_by_team[team_a]:
                        for spread_b in spreads_by_team[team_b]:
                            if spread_a["bookmaker"] == spread_b["bookmaker"]:
                                continue

                            # Team A с отрицательным спредом, Team B с положительным
                            # Коридор: |spread_a| < spread_b (по модулю)
                            line_a = spread_a["line"]  # e.g. -3.5
                            line_b = spread_b["line"]  # e.g. +4.5

                            # Коридор существует если абс(line_a) < line_b
                            # то есть line_a отрицательный, line_b положительный
                            if line_a < 0 and line_b > 0 and abs(line_a) < line_b:
                                corridor_low = abs(line_a)
                                corridor_high = line_b

                                # Расчет
                                stake_total = 2.0
                                worst_case_loss_pct = -100.0
                                payout_a = spread_a["odds"]
                                payout_b = spread_b["odds"]
                                best_case_profit = (payout_a + payout_b) - stake_total
                                best_case_profit_pct = (best_case_profit / stake_total) * 100.0

                                corridor_width = corridor_high - corridor_low
                                middle_probability = (
                                    corridor_width / corridor_high
                                    if corridor_high > 0 else 0.0
                                )

                                expected_value_pct = (
                                    best_case_profit_pct * middle_probability
                                    + worst_case_loss_pct * (1.0 - middle_probability)
                                )

                                opp = MiddleOpportunity(
                                    type="middle_spreads",
                                    sport=sport,
                                    event_name=event_name,
                                    home=home,
                                    away=away,
                                    leg1={
                                        "bookmaker": spread_a["bookmaker"],
                                        "market": "spreads",
                                        "line": line_a,
                                        "odds": spread_a["odds"],
                                        "outcome": team_a,
                                    },
                                    leg2={
                                        "bookmaker": spread_b["bookmaker"],
                                        "market": "spreads",
                                        "line": line_b,
                                        "odds": spread_b["odds"],
                                        "outcome": team_b,
                                    },
                                    middle_range=[corridor_low, corridor_high],
                                    middle_probability=middle_probability,
                                    worst_case_loss_pct=worst_case_loss_pct,
                                    best_case_profit_pct=best_case_profit_pct,
                                    expected_value_pct=expected_value_pct,
                                )
                                opportunities.append(opp)
                                logger.info(
                                    "Middle (spreads): %s | коридор [%.1f, %.1f] | EV %.2f%%",
                                    event_name, corridor_low, corridor_high, expected_value_pct,
                                )

        return opportunities

    def find_middles_asian(self, events: list[dict[str, Any]]) -> list[MiddleOpportunity]:
        """Ищет middle-возможности на азиатских гандикапах.

        Placeholder - пока не реализовано (требует данных по Asian Handicap).

        Args:
            events: нормализованные события из OddsAPI

        Returns:
            Пустой список (заглушка)
        """
        logger.debug("find_middles_asian: placeholder, возвращаем пустой список")
        return []

    async def estimate_middle_probability(
        self,
        session: Any,
        opp: MiddleOpportunity,
    ) -> float:
        """Оценивает вероятность попадания в коридор с помощью AI.

        Использует LLM для более точной оценки probability на основе
        спорта, лиги, команд и ширины коридора.

        Args:
            session: aiohttp.ClientSession для AI-запроса
            opp: Middle-возможность для оценки

        Returns:
            Уточненная вероятность (0.0 - 1.0)
        """
        acquired = await _rate_limiter.acquire(priority="NORMAL", timeout=30.0)
        if not acquired:
            logger.warning(
                "AI rate limit: не удалось получить токен для estimate_middle_probability"
            )
            return opp.middle_probability

        prompt = (
            f"Оцени вероятность (от 0.0 до 1.0) того, что результат матча "
            f"попадёт в коридор [{opp.middle_range[0]}, {opp.middle_range[1]}].\n"
            f"Спорт: {opp.sport}\n"
            f"Матч: {opp.event_name}\n"
            f"Тип коридора: {opp.type}\n"
            f"Leg1: {opp.leg1}\n"
            f"Leg2: {opp.leg2}\n"
            f"Ответь ТОЛЬКО JSON: {{\"probability\": <float>}}"
        )

        try:
            if ai_router is None:
                logger.warning("ai_router недоступен, используем наивную вероятность")
                return opp.middle_probability
            result = await ai_router.call_llm_json(session, prompt)
            probability = float(result.get("probability", opp.middle_probability))
            probability = max(0.0, min(1.0, probability))
            logger.info(
                "AI estimate middle probability: %s -> %.3f",
                opp.event_name, probability,
            )
            return probability
        except Exception as e:
            logger.warning("AI estimate_middle_probability ошибка: %s", e)
            return opp.middle_probability
