"""Ранжирование арбитражных возможностей по составному скору.

ArbRanker вычисляет composite_score на основе:
  - profit_pct (прибыльность)
  - ai_score (оценка AI-фильтра)
  - liquidity_factor (ликвидность лиги)
  - freshness_factor (свежесть обнаружения)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Лиги с высокой ликвидностью (factor = 1.0)
_MAJOR_LEAGUES: set[str] = {
    "soccer_epl",
    "basketball_nba",
    "tennis_atp",
    "soccer_uefa_champs_league",
    "basketball_euroleague",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
}

# Параметры свежести
_FRESHNESS_MAX_AGE_SEC: float = 300.0  # 5 минут
_FRESHNESS_MIN: float = 0.5  # минимальное значение при 300с


class ArbRanker:
    """Ранжирует арбитражные возможности по составному скору."""

    def __init__(self, top_n: int = 10) -> None:
        self._top_n: int = top_n

    def rank(self, opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Вычисляет composite_score и сортирует возможности.

        composite_score = profit_pct * (ai_score / 100) * liquidity_factor * freshness_factor

        Args:
            opportunities: список арбитражных возможностей (dict)

        Returns:
            Отсортированный список (top N) с добавленным composite_score
        """
        scored: list[dict[str, Any]] = []

        for opp in opportunities:
            profit_pct: float = opp.get("profit_pct", 0.0) or opp.get("edge_pct", 0.0)
            ai_score: int = opp.get("ai_score", 50)
            sport: str = opp.get("sport", "")

            liquidity: float = self._liquidity_factor(sport)
            freshness: float = self._freshness_factor(opp)

            composite: float = profit_pct * (ai_score / 100.0) * liquidity * freshness
            opp["composite_score"] = round(composite, 4)
            scored.append(opp)

        # Сортировка по убыванию composite_score
        scored.sort(key=lambda x: x.get("composite_score", 0.0), reverse=True)

        top = scored[: self._top_n]
        logger.info(
            "Ranker: %d возможностей отранжировано, топ %d отобрано",
            len(scored), len(top),
        )
        return top

    @staticmethod
    def _liquidity_factor(sport: str) -> float:
        """Фактор ликвидности: 1.0 для major leagues, 0.6 для остальных."""
        if sport in _MAJOR_LEAGUES:
            return 1.0
        return 0.6

    @staticmethod
    def _freshness_factor(opportunity: dict[str, Any]) -> float:
        """Фактор свежести: 1.0 при 0с, линейно убывает до 0.5 при 300с.

        Если timestamp отсутствует или не парсится, возвращает 0.75 (нейтрально).
        """
        timestamp_str: str = opportunity.get("timestamp", "")
        if not timestamp_str:
            return 0.75

        try:
            detected_time = datetime.fromisoformat(timestamp_str)
            if detected_time.tzinfo is None:
                detected_time = detected_time.replace(tzinfo=timezone.utc)
            age_sec: float = (datetime.now(timezone.utc) - detected_time).total_seconds()
        except (ValueError, TypeError):
            return 0.75

        if age_sec <= 0:
            return 1.0
        if age_sec >= _FRESHNESS_MAX_AGE_SEC:
            return _FRESHNESS_MIN

        # Линейная интерполяция: 1.0 -> 0.5 за 300с
        factor: float = 1.0 - (1.0 - _FRESHNESS_MIN) * (age_sec / _FRESHNESS_MAX_AGE_SEC)
        return factor
