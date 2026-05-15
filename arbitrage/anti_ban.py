"""Анти-бан движок: эвристики для обхода обнаружения букмекерами.

Обеспечивает:
  - Случайные задержки между ставками
  - Ограничение частоты ставок по букмекерам
  - Генерация шумовых ставок для маскировки
  - Имитация человеческого поведения
  - Контроль временных окон для ставок
"""

from __future__ import annotations

import random
import time
from typing import Any


# Максимум ставок на одного букмекера в час
_MAX_BETS_PER_HOUR: int = 5

# Окно разрешённых часов для ставок (UTC)
_BETTING_WINDOW_START: int = 8
_BETTING_WINDOW_END: int = 23


class AntiBanEngine:
    """Эвристики для минимизации риска блокировки аккаунтов."""

    def __init__(self, max_bets_per_hour: int = _MAX_BETS_PER_HOUR) -> None:
        self._max_bets_per_hour = max_bets_per_hour
        self._history: dict[str, list[float]] = {}

    def should_delay(self) -> float:
        """Вернуть случайную задержку (2-15 секунд) перед размещением ставки."""
        return random.uniform(2.0, 15.0)

    def simulate_human_pattern(self) -> float:
        """Вернуть джиттер 0.5-3.0 секунды для имитации человеческого поведения."""
        return random.uniform(0.5, 3.0)

    def generate_noise_bet(self) -> dict[str, Any]:
        """Генерация шумовой ставки для маскировки арбитражной активности.

        Возвращает словарь с параметрами правдоподобной casual-ставки:
        популярный матч, фаворит, небольшая сумма.
        """
        events = [
            {"event": "Реал Мадрид - Барселона", "sport": "soccer"},
            {"event": "Манчестер Сити - Ливерпуль", "sport": "soccer"},
            {"event": "ПСЖ - Марсель", "sport": "soccer"},
            {"event": "Бавария - Дортмунд", "sport": "soccer"},
            {"event": "Лейкерс - Уорриорз", "sport": "basketball"},
            {"event": "Джокович - Алькараз", "sport": "tennis"},
            {"event": "Челси - Арсенал", "sport": "soccer"},
            {"event": "Интер - Милан", "sport": "soccer"},
        ]

        chosen = random.choice(events)
        stake = round(random.uniform(5.0, 25.0), 2)
        odds = round(random.uniform(1.20, 1.80), 2)

        return {
            "event": chosen["event"],
            "sport": chosen["sport"],
            "outcome": "фаворит",
            "stake": stake,
            "odds": odds,
            "type": "noise",
            "reason": "маскировка арбитражной активности",
        }

    def check_frequency(self, bookmaker: str) -> bool:
        """Проверить, не превышен ли лимит ставок на букмекера.

        Возвращает True если можно ставить (лимит не превышен).
        Возвращает False если превышен лимит ставок в час.
        """
        now = time.time()
        one_hour_ago = now - 3600.0

        # Очистка старых записей
        if bookmaker in self._history:
            self._history[bookmaker] = [
                ts for ts in self._history[bookmaker] if ts > one_hour_ago
            ]
        else:
            self._history[bookmaker] = []

        count = len(self._history[bookmaker])
        return count < self._max_bets_per_hour

    def record_bet(self, bookmaker: str) -> None:
        """Зафиксировать факт размещения ставки у букмекера."""
        now = time.time()
        if bookmaker not in self._history:
            self._history[bookmaker] = []
        self._history[bookmaker].append(now)

    def get_betting_window(self) -> tuple[int, int]:
        """Вернуть разрешённое окно часов для ставок (UTC).

        Не рекомендуется ставить с 00:00 до 07:59 - подозрительная активность.
        """
        return (_BETTING_WINDOW_START, _BETTING_WINDOW_END)
