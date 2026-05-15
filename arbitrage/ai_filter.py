"""AI-фильтр арбитражных возможностей.

Использует LLM (через корневой ai_router) для оценки вероятности того,
что найденный арбитраж реальный, а не ловушка букмекера.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Optional

import aiohttp

# Импорт ai_router из корневого проекта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_router  # noqa: E402


# TTL кэша результатов (секунды)
_CACHE_TTL: int = 300  # 5 минут


class ArbFilter:
    """Оценивает арбитражные возможности через LLM."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def _cache_key(self, opportunity: dict[str, Any]) -> str:
        """Генерация ключа кэша из основных параметров возможности."""
        parts = [
            str(opportunity.get("sport", "")),
            str(opportunity.get("event", "")),
            str(opportunity.get("bookmakers", "")),
            str(opportunity.get("profit_pct", "")),
        ]
        return "|".join(parts)

    def _get_cached(self, key: str) -> Optional[dict[str, Any]]:
        """Получить результат из кэша, если TTL не истёк."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, result = entry
        if time.time() - ts > _CACHE_TTL:
            del self._cache[key]
            return None
        return result

    def _set_cached(self, key: str, result: dict[str, Any]) -> None:
        """Сохранить результат в кэш."""
        self._cache[key] = (time.time(), result)

    async def evaluate(self, opportunity: dict[str, Any]) -> dict[str, Any]:
        """Оценить арбитражную возможность через LLM.

        Возвращает dict с ключами:
          - score: int 0-100 (вероятность что арб живой)
          - reasoning: str (обоснование)
          - is_live: bool (score > 50)
        """
        cache_key = self._cache_key(opportunity)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        prompt = self._build_prompt(opportunity)

        try:
            resp = await ai_router.call_llm_json(
                self._session,
                prompt,
                max_output_tokens=256,
                temperature=0.2,
                timeout=20,
            )
        except Exception as exc:
            print(f"[AI_FILTER] Ошибка вызова LLM: {exc}")
            resp = None

        if resp is None:
            # AI недоступен - возвращаем нейтральную оценку
            result: dict[str, Any] = {
                "score": 50,
                "reasoning": "AI-оценка недоступна",
                "is_live": False,
            }
            return result

        score = int(resp.get("score", 50))
        score = max(0, min(100, score))
        reasoning = str(resp.get("reasoning", "нет обоснования"))

        result = {
            "score": score,
            "reasoning": reasoning,
            "is_live": score > 50,
        }

        self._set_cached(cache_key, result)
        return result

    def _build_prompt(self, opportunity: dict[str, Any]) -> str:
        """Сформировать промпт для LLM-оценки арбитража."""
        sport = opportunity.get("sport", "неизвестно")
        event = opportunity.get("event", "неизвестно")
        bookmakers = opportunity.get("bookmakers", [])
        profit_pct = opportunity.get("profit_pct", 0.0)
        odds = opportunity.get("odds", {})
        time_to_event = opportunity.get("time_to_event_min", "неизвестно")
        line_movement = opportunity.get("line_movement", "нет данных")

        prompt = (
            "Ты - эксперт по спортивным ставкам и арбитражу. "
            "Оцени вероятность того, что данная арбитражная возможность реальна "
            "(а не ловушка букмекера или устаревшая линия).\n\n"
            f"Спорт: {sport}\n"
            f"Событие: {event}\n"
            f"Букмекеры: {bookmakers}\n"
            f"Коэффициенты: {odds}\n"
            f"Прибыль: {profit_pct:.2f}%\n"
            f"Время до события: {time_to_event} мин\n"
            f"Движение линии: {line_movement}\n\n"
            "Учитывай:\n"
            "1. Скорость движения линии (быстрое движение = высокий риск)\n"
            "2. Репутация букмекера (soft vs sharp bookmaker)\n"
            "3. Тип спорта (теннис/live = выше риск устаревших коэфф.)\n"
            "4. Размер расхождения (слишком большой = вероятно ловушка)\n"
            "5. Время до события (чем ближе, тем быстрее меняются линии)\n\n"
            "Ответь строго в формате JSON:\n"
            '{"score": <0-100>, "reasoning": "<краткое обоснование на русском>"}\n'
            "score = вероятность что арбитраж реален и доступен для исполнения."
        )
        return prompt
