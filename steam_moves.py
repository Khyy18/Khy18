"""Детектор Steam Moves - обнаружение резких движений линий у sharp-букмекеров.

Отслеживает изменения коэффициентов Pinnacle и находит мягких букмекеров,
которые ещё не скорректировали свои линии (stale odds).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Букмекеры, считающиеся sharp (эталонными)
SHARP_BOOKMAKERS: set[str] = {"pinnacle"}

# Порог для определения steam move (изменение implied probability)
STEAM_THRESHOLD: float = 0.03

# Максимальное количество снимков в истории на каждый ключ
MAX_HISTORY_SNAPSHOTS: int = 10

# Максимальный возраст записи в секундах (24 часа) для пруниинга
MAX_HISTORY_AGE_SEC: float = 86400.0


@dataclass
class SteamOpportunity:
    """Возможность на основе steam move (резкого движения sharp-линии)."""

    event_name: str                    # название события
    sport: str                         # вид спорта
    home: str                          # домашняя команда
    away: str                          # гостевая команда
    sharp_movement: float              # величина движения (implied prob diff)
    direction: str                     # "up" или "down"
    stale_bookmakers: list[dict[str, Any]]  # [{bookmaker, current_odds, expected_odds, edge_pct}]
    time_since_move_sec: float = 0.0   # секунд с момента движения
    confidence: int = 0                # уверенность 0-100
    timestamp: str = ""                # время обнаружения (ISO format)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class SteamDetector:
    """Детектор steam moves на основе истории sharp-букмекеров."""

    def __init__(self) -> None:
        """Инициализация детектора.

        _sharp_history хранит историю коэффициентов sharp-букмекеров:
        {event_id::outcome -> [(timestamp, odds), ...]}
        """
        self._sharp_history: dict[str, list[tuple[float, float]]] = {}

    def _prune_stale_keys(self) -> None:
        """Удаляет ключи с устаревшими записями из _sharp_history.

        Ключ считается устаревшим, если все его записи старше MAX_HISTORY_AGE_SEC.
        """
        now = time.time()
        stale_keys: list[str] = []
        for key, history in self._sharp_history.items():
            if not history:
                stale_keys.append(key)
                continue
            # Последняя запись - самая свежая
            latest_ts = history[-1][0]
            if now - latest_ts > MAX_HISTORY_AGE_SEC:
                stale_keys.append(key)
        for key in stale_keys:
            del self._sharp_history[key]
        if stale_keys:
            logger.debug(
                "Pruned %d stale keys from sharp history", len(stale_keys)
            )

    def update_sharp_snapshot(self, events: list[dict[str, Any]]) -> None:
        """Обновляет историю коэффициентов sharp-букмекеров.

        Извлекает текущие коэффициенты Pinnacle из событий
        и сохраняет их с текущей временной меткой.

        Args:
            events: нормализованные события из OddsAPI
        """
        now = time.time()

        # Удаляем устаревшие ключи для предотвращения утечки памяти
        self._prune_stale_keys()

        for event in events:
            event_id: str = event.get("id", "")
            if not event_id:
                continue

            for bm in event.get("bookmakers", []):
                bm_key: str = bm.get("key", "")
                if bm_key.lower() not in SHARP_BOOKMAKERS:
                    continue

                for market in bm.get("markets", []):
                    market_key: str = market.get("key", "")
                    for outcome in market.get("outcomes", []):
                        name: str = outcome.get("name", "")
                        price: float = outcome.get("price", 0.0)
                        if not name or price <= 1.0:
                            continue

                        key = f"{event_id}::{name}"
                        if key not in self._sharp_history:
                            self._sharp_history[key] = []

                        history = self._sharp_history[key]
                        history.append((now, price))

                        # Ограничиваем историю
                        if len(history) > MAX_HISTORY_SNAPSHOTS:
                            self._sharp_history[key] = history[-MAX_HISTORY_SNAPSHOTS:]

        logger.debug(
            "Sharp snapshot обновлён: %d ключей в истории",
            len(self._sharp_history),
        )

    def detect_steam(
        self,
        events: list[dict[str, Any]],
        sharp_probs: dict[str, list[float]],
    ) -> list[SteamOpportunity]:
        """Обнаруживает steam moves и находит stale-букмекеров.

        Сравнивает текущие коэффициенты Pinnacle с предыдущим снимком.
        Если движение > STEAM_THRESHOLD, проверяет soft-букмекеров
        на наличие устаревших линий.

        Args:
            events: нормализованные события из OddsAPI
            sharp_probs: словарь {event_id: [fair_prob_1, ...]} (не используется напрямую,
                         но передаётся для совместимости с API)

        Returns:
            Список SteamOpportunity с обнаруженными steam moves
        """
        opportunities: list[SteamOpportunity] = []
        now = time.time()

        for event in events:
            event_id: str = event.get("id", "")
            sport: str = event.get("sport", "")
            home: str = event.get("home_team", "")
            away: str = event.get("away_team", "")
            event_name: str = f"{home} vs {away}"

            if not event_id:
                continue

            # Извлекаем текущие Pinnacle-коэффициенты
            current_sharp: dict[str, float] = {}
            for bm in event.get("bookmakers", []):
                bm_key: str = bm.get("key", "")
                if bm_key.lower() not in SHARP_BOOKMAKERS:
                    continue
                for market in bm.get("markets", []):
                    if market.get("key") != "h2h":
                        continue
                    for outcome in market.get("outcomes", []):
                        name: str = outcome.get("name", "")
                        price: float = outcome.get("price", 0.0)
                        if name and price > 1.0:
                            current_sharp[name] = price

            if not current_sharp:
                continue

            # Проверяем каждый исход на наличие steam move
            for outcome_name, current_odds in current_sharp.items():
                key = f"{event_id}::{outcome_name}"
                history = self._sharp_history.get(key, [])

                if len(history) < 2:
                    continue

                # Берём предпоследний снимок (последний - текущий)
                prev_ts, prev_odds = history[-2]

                if prev_odds <= 1.0 or current_odds <= 1.0:
                    continue

                # Вычисляем изменение implied probability
                prev_prob = 1.0 / prev_odds
                current_prob = 1.0 / current_odds
                movement = current_prob - prev_prob

                if abs(movement) < STEAM_THRESHOLD:
                    continue

                # Steam move обнаружен
                direction = "up" if movement > 0 else "down"
                time_since_move = now - prev_ts

                # Ищем stale soft-букмекеров
                stale_bookmakers: list[dict[str, Any]] = []
                for bm in event.get("bookmakers", []):
                    bm_key: str = bm.get("key", "")
                    if bm_key.lower() in SHARP_BOOKMAKERS:
                        continue

                    for market in bm.get("markets", []):
                        if market.get("key") != "h2h":
                            continue
                        for out in market.get("outcomes", []):
                            if out.get("name") != outcome_name:
                                continue
                            soft_odds: float = out.get("price", 0.0)
                            if soft_odds <= 1.0:
                                continue

                            # Ожидаемые коэффициенты soft должны быть ~= current sharp
                            expected_odds = current_odds
                            soft_prob = 1.0 / soft_odds
                            edge_pct = (soft_odds * current_prob - 1.0) * 100.0

                            # Если soft не скорректировался (edge > 0)
                            if edge_pct > 0:
                                stale_bookmakers.append({
                                    "bookmaker": bm_key,
                                    "current_odds": soft_odds,
                                    "expected_odds": round(expected_odds, 3),
                                    "edge_pct": round(edge_pct, 2),
                                })

                if not stale_bookmakers:
                    continue

                # Уверенность на основе величины движения и количества stale бк
                confidence = min(100, int(abs(movement) / STEAM_THRESHOLD * 30 + len(stale_bookmakers) * 15))

                opp = SteamOpportunity(
                    event_name=event_name,
                    sport=sport,
                    home=home,
                    away=away,
                    sharp_movement=round(abs(movement), 4),
                    direction=direction,
                    stale_bookmakers=stale_bookmakers,
                    time_since_move_sec=round(time_since_move, 1),
                    confidence=confidence,
                )
                opportunities.append(opp)
                logger.info(
                    "Steam move: %s | %s %s %.4f | stale: %d бк | confidence: %d",
                    event_name, outcome_name, direction,
                    abs(movement), len(stale_bookmakers), confidence,
                )

        return opportunities
