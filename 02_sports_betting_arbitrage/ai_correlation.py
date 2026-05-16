"""Анализатор корреляций между событиями.

Использует LLM для определения зависимостей между
спортивными событиями в рамках одного турнира/лиги.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Optional

import aiohttp

# Импорт ai_router из корневого проекта
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)
try:
    import ai_router
except ImportError:
    ai_router = None  # type: ignore

logger = logging.getLogger(__name__)


class EventCorrelation:
    """Анализатор корреляций между спортивными событиями."""

    async def find_correlations(
        self,
        session: aiohttp.ClientSession,
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Найти корреляции между событиями.

        Группирует события по спорту/лиге и для групп из 2+ событий
        запрашивает LLM-анализ корреляций.

        Args:
            session: aiohttp сессия.
            events: список событий для анализа.

        Returns:
            Список словарей с ключами: event_a, event_b, correlation_strength, impact_direction.
        """
        if not events or ai_router is None:
            return []

        # Группируем по спорту
        groups: dict[str, list[dict[str, Any]]] = {}
        for evt in events:
            sport = str(evt.get("sport", "unknown"))
            groups.setdefault(sport, []).append(evt)

        correlations: list[dict[str, Any]] = []

        for sport, group_events in groups.items():
            if len(group_events) < 2:
                continue

            group_correlations = await self._analyze_group(session, sport, group_events)
            correlations.extend(group_correlations)

        logger.info("EventCorrelation: найдено %d корреляций", len(correlations))
        return correlations

    async def _analyze_group(
        self,
        session: aiohttp.ClientSession,
        sport: str,
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Проанализировать группу событий одного спорта на корреляции."""
        if ai_router is None:
            return []

        # Формируем описание событий
        events_desc = []
        for evt in events[:10]:  # ограничиваем размер промпта
            name = evt.get("event", evt.get("name", "неизвестно"))
            events_desc.append(str(name))

        prompt = (
            "Ты - эксперт по спортивной аналитике. "
            "Определи, есть ли корреляции между этими событиями "
            "(одна команда в нескольких матчах, турнирная логика, и т.п.).\n\n"
            f"Спорт: {sport}\n"
            f"События:\n"
        )
        for i, desc in enumerate(events_desc, 1):
            prompt += f"  {i}. {desc}\n"

        prompt += (
            "\nЕсли есть корреляции, ответь в формате JSON:\n"
            '{"correlations": [{"event_a": "<событие 1>", "event_b": "<событие 2>", '
            '"correlation_strength": <0.0-1.0>, '
            '"impact_direction": "<описание как результат A влияет на B>"}]}\n\n'
            "Если корреляций нет, ответь:\n"
            '{"correlations": []}'
        )

        try:
            resp = await ai_router.call_llm_json(
                session,
                prompt,
                max_output_tokens=256,
                temperature=0.2,
                timeout=25,
            )
        except Exception as exc:
            logger.warning("Ошибка LLM в EventCorrelation: %s", exc)
            return []

        if resp is None:
            return []

        raw_correlations = resp.get("correlations", [])
        if not isinstance(raw_correlations, list):
            return []

        results: list[dict[str, Any]] = []
        for corr in raw_correlations:
            if not isinstance(corr, dict):
                continue
            event_a = str(corr.get("event_a", ""))
            event_b = str(corr.get("event_b", ""))
            if not event_a or not event_b:
                continue

            strength = float(corr.get("correlation_strength", 0.0))
            strength = max(0.0, min(1.0, strength))

            impact_direction = str(corr.get("impact_direction", ""))

            results.append({
                "event_a": event_a,
                "event_b": event_b,
                "correlation_strength": strength,
                "impact_direction": impact_direction,
            })

        return results


async def correlation_loop(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
    """Фоновый цикл анализа корреляций (каждый час).

    Анализирует активные арбитражи на предмет корреляций.
    """
    from arbitrage import memory

    analyzer = EventCorrelation()
    interval = 3600  # 1 час

    while True:
        try:
            active_arbs = memory.get_active_arbs()
            if active_arbs:
                correlations = await analyzer.find_correlations(session, active_arbs)
                state["correlations"] = correlations
                if correlations:
                    logger.info("correlation_loop: найдено %d корреляций", len(correlations))
        except Exception as exc:
            logger.error("correlation_loop ошибка: %s", exc)

        await asyncio.sleep(interval)
