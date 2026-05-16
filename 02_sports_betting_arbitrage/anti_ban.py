"""Анти-бан движок: эвристики для обхода обнаружения букмекерами.

Обеспечивает:
  - Случайные задержки между ставками
  - Ограничение частоты ставок по букмекерам
  - Генерация шумовых ставок для маскировки
  - Имитация человеческого поведения
  - Контроль временных окон для ставок
  - AI-генерация поведенческих профилей
  - Гуманизация сумм ставок
  - Корреляционная защита
  - Детектирование пре-бана
  - Адаптивные задержки по типу букмекера
"""

from __future__ import annotations

import os
import random
import sys
import time
from typing import Any, Optional

_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)
try:
    import ai_router
except ImportError:
    ai_router = None


# Максимум ставок на одного букмекера в час
_MAX_BETS_PER_HOUR: int = 5

# Окно разрешённых часов для ставок (UTC)
_BETTING_WINDOW_START: int = 8
_BETTING_WINDOW_END: int = 23

# Классификация букмекеров
_SHARP_BOOKMAKERS: set[str] = {"pinnacle", "betfair"}
_SOFT_BOOKMAKERS: set[str] = {"bet365", "1xbet", "unibet", "marathonbet"}

# Корреляционное окно (5 минут)
_CORRELATION_WINDOW_SEC: float = 300.0


class AntiBanEngine:
    """Эвристики для минимизации риска блокировки аккаунтов."""

    def __init__(self, max_bets_per_hour: int = _MAX_BETS_PER_HOUR) -> None:
        self._max_bets_per_hour = max_bets_per_hour
        self._history: dict[str, list[float]] = {}
        self._correlation_history: dict[tuple[str, str], float] = {}
        self._acceptance_times: dict[str, list[float]] = {}

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

    # --- Расширенные методы анти-бана ---

    async def generate_behavior_profile(
        self, session: Any, bookmaker: str
    ) -> dict[str, Any]:
        """Генерация поведенческого профиля для букмекера через AI.

        Возвращает рекомендации по таймингу ставок, паттернам сумм,
        видам спорта для ставок.
        """
        if ai_router is None:
            return {
                "bet_timing": "random 5-30 min intervals",
                "stake_pattern": "varied, non-round",
                "sports": ["soccer", "basketball"],
                "session_duration_min": 15,
            }

        prompt = (
            f"Ты эксперт по поведенческим паттернам ставок. "
            f"Сгенерируй поведенческий профиль обычного игрока для букмекера '{bookmaker}'. "
            f"Ответь в JSON формате с ключами: "
            f"bet_timing (строка - рекомендация по интервалам между ставками), "
            f"stake_pattern (строка - как варьировать суммы), "
            f"sports (список видов спорта для ставок), "
            f"session_duration_min (число - продолжительность сессии в минутах), "
            f"avoid_patterns (список паттернов, которых стоит избегать)."
        )
        try:
            result = await ai_router.call_llm_json(session, prompt)
            if isinstance(result, dict):
                return result
        except Exception as exc:  # noqa: BLE001
            print(f"[ANTI_BAN] Ошибка генерации профиля для {bookmaker}: {exc}")

        return {
            "bet_timing": "random 5-30 min intervals",
            "stake_pattern": "varied, non-round",
            "sports": ["soccer", "basketball"],
            "session_duration_min": 15,
        }

    def humanize_stake(self, target_amount: float) -> float:
        """Рандомизация суммы ставки для имитации человеческого поведения.

        Добавляет шум +/-5-15% к целевой сумме и избегает круглых чисел.
        Например, $50.00 -> $47.83 или $53.17.
        """
        # Случайное отклонение от 5% до 15%
        noise_pct = random.uniform(0.05, 0.15)
        # Случайный знак
        if random.random() < 0.5:
            noise_pct = -noise_pct

        amount = target_amount * (1.0 + noise_pct)

        # Избегаем круглых чисел (кратных 5 или 10)
        int_part = int(amount)
        if int_part % 5 == 0:
            # Сдвигаем целую часть на 1-3
            int_part += random.choice([1, 2, 3, -1, -2, -3])

        # Добавляем случайные копейки (не .00)
        cents = random.randint(1, 99)
        amount = int_part + cents / 100.0

        # Гарантируем пределы +/-15%
        min_amount = target_amount * 0.85
        max_amount = target_amount * 1.15
        amount = max(min_amount, min(max_amount, amount))

        return round(amount, 2)

    def check_correlation(self, bookmaker: str, event_id: str) -> bool:
        """Проверка корреляции: не более 1 ставки на (букмекер, событие) за 5 минут.

        Возвращает True если можно ставить (нет корреляции).
        Возвращает False если уже была ставка на это событие у этого букмекера
        в последние 5 минут.
        """
        now = time.time()
        key = (bookmaker.lower(), event_id)

        last_bet_time = self._correlation_history.get(key)
        if last_bet_time is not None:
            elapsed = now - last_bet_time
            if elapsed < _CORRELATION_WINDOW_SEC:
                print(
                    f"[ANTI_BAN] Корреляция: ставка на {bookmaker}/{event_id} "
                    f"была {elapsed:.0f}с назад (лимит {_CORRELATION_WINDOW_SEC:.0f}с)"
                )
                return False

        # Записываем время ставки
        self._correlation_history[key] = now
        return True

    def detect_pre_ban(self, bookmaker: str) -> tuple[bool, str]:
        """Детектирование паттерна пре-бана букмекера.

        Проверяет: если последние 3 времени приёма ставок у букмекера
        больше чем 2x от среднего (исключая последние 3), это сигнал о скором бане.

        Возвращает (is_pre_ban, detail_message).
        """
        bm_key = bookmaker.lower()
        times = self._acceptance_times.get(bm_key, [])

        if len(times) < 4:
            return False, ""

        # Среднее время по записям кроме последних 3 (базовый уровень)
        baseline = times[:-3]
        if not baseline:
            return False, ""

        avg_time = sum(baseline) / len(baseline)
        if avg_time <= 0:
            return False, ""

        # Последние 3 значения
        last_3 = times[-3:]
        threshold = avg_time * 2.0

        # Проверяем все ли последние 3 превышают порог
        all_above = all(t > threshold for t in last_3)

        if all_above:
            detail = (
                f"Букмекер {bookmaker}: последние 3 приёма ставок "
                f"({last_3[0]:.1f}с, {last_3[1]:.1f}с, {last_3[2]:.1f}с) "
                f"превышают 2x среднее ({avg_time:.1f}с). "
                f"Возможен скорый бан аккаунта."
            )
            return True, detail

        return False, ""

    def record_acceptance_time(self, bookmaker: str, duration_sec: float) -> None:
        """Записать время приёма ставки букмекером.

        Args:
            bookmaker: название букмекера
            duration_sec: время в секундах от отправки до приёма ставки
        """
        bm_key = bookmaker.lower()
        if bm_key not in self._acceptance_times:
            self._acceptance_times[bm_key] = []
        self._acceptance_times[bm_key].append(duration_sec)

        # Ограничиваем историю последними 50 записями
        if len(self._acceptance_times[bm_key]) > 50:
            self._acceptance_times[bm_key] = self._acceptance_times[bm_key][-50:]

    def get_adaptive_delay(self, bookmaker: str) -> float:
        """Адаптивная задержка на основе типа букмекера.

        Sharp букмекеры (pinnacle, betfair): 10-30 секунд.
        Soft букмекеры (bet365, 1xbet, unibet, marathonbet): 3-8 секунд.
        Неизвестные: 5-15 секунд.
        """
        bm_lower = bookmaker.lower()

        if bm_lower in _SHARP_BOOKMAKERS:
            return random.uniform(10.0, 30.0)
        elif bm_lower in _SOFT_BOOKMAKERS:
            return random.uniform(3.0, 8.0)
        else:
            return random.uniform(5.0, 15.0)

    async def generate_noise_strategy(
        self, session: Any, bookmaker: str
    ) -> dict[str, Any]:
        """AI-решение о необходимости шумовой ставки перед реальной.

        Возвращает словарь с рекомендацией: нужна ли шумовая ставка,
        и если да, параметры (спорт, тип, приблизительная сумма).
        """
        if ai_router is None:
            # Без AI - решаем случайно (20% шанс шумовой ставки)
            need_noise = random.random() < 0.2
            return {
                "need_noise": need_noise,
                "sport": "soccer" if need_noise else None,
                "bet_type": "favourite" if need_noise else None,
                "stake_range": [5, 20] if need_noise else None,
            }

        prompt = (
            f"Ты эксперт по обходу систем обнаружения букмекеров. "
            f"Нужно решить, стоит ли сделать шумовую (маскировочную) ставку "
            f"перед реальной арбитражной ставкой у букмекера '{bookmaker}'. "
            f"Ответь в JSON: need_noise (bool), sport (строка или null), "
            f"bet_type (строка или null), stake_range ([min, max] или null), "
            f"reason (строка - объяснение решения)."
        )
        try:
            result = await ai_router.call_llm_json(session, prompt)
            if isinstance(result, dict):
                return result
        except Exception as exc:  # noqa: BLE001
            print(f"[ANTI_BAN] Ошибка генерации noise-стратегии для {bookmaker}: {exc}")

        return {
            "need_noise": False,
            "sport": None,
            "bet_type": None,
            "stake_range": None,
        }
