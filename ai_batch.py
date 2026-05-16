"""AI Batch Scorer - пакетная оценка арбитражных возможностей.

Группирует возможности в батчи и отправляет один запрос к LLM
для оценки нескольких возможностей за раз. Экономит квоту API.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import aiohttp

from arbitrage.ai_rate_limiter import AiRateLimiter
from arbitrage.config import AI_BATCH_SIZE

# Импорт ai_router из корневого проекта
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)
try:
    import ai_router
except ImportError:
    ai_router = None  # type: ignore

logger = logging.getLogger(__name__)


class AiBatchScorer:
    """Пакетная оценка арбитражных возможностей через LLM."""

    def __init__(self, rate_limiter: AiRateLimiter | None = None) -> None:
        """Инициализация batch scorer.

        Args:
            rate_limiter: экземпляр AiRateLimiter (создается автоматически если None).
        """
        self._rate_limiter: AiRateLimiter = rate_limiter or AiRateLimiter()
        self._batch_size: int = AI_BATCH_SIZE

    def _build_prompt(self, batch: list[dict[str, Any]]) -> str:
        """Формирует промпт для оценки батча возможностей.

        Args:
            batch: список возможностей для оценки.

        Returns:
            Строка промпта для LLM.
        """
        opps_text = ""
        for i, opp in enumerate(batch):
            sport = opp.get("sport", "unknown")
            event = opp.get("event", "unknown")
            profit = opp.get("profit_pct", 0.0)
            bookmakers = opp.get("bookmakers", [])
            odds = opp.get("odds", {})
            opps_text += (
                f"  {i}: sport={sport}, event={event}, "
                f"profit={profit:.2f}%, bookmakers={bookmakers}, odds={odds}\n"
            )

        prompt = (
            f"Evaluate these {len(batch)} arbitrage opportunities. "
            f"For each one, assess the likelihood it is a real profitable arbitrage "
            f"vs a bookmaker trap or stale line.\n\n"
            f"Opportunities:\n{opps_text}\n"
            f"Return a JSON array with exactly {len(batch)} items: "
            f'[{{"id": 0, "score": 85, "reasoning": "..."}}, ...]\n'
            f"Score 0-100 where 100 = definitely real arb, 0 = definitely fake/trap.\n"
            f"Return ONLY the JSON array, no other text."
        )
        return prompt

    async def score_batch(
        self,
        opportunities: list[dict[str, Any]],
        session: aiohttp.ClientSession,
    ) -> list[dict[str, Any]]:
        """Оценить список возможностей пакетно через LLM.

        Args:
            opportunities: список словарей с арбитражными возможностями.
            session: aiohttp сессия для HTTP запросов.

        Returns:
            Список словарей с оценками [{id, score, reasoning}, ...].
        """
        if not opportunities:
            return []

        results: list[dict[str, Any]] = []

        # Разбиваем на батчи
        for batch_start in range(0, len(opportunities), self._batch_size):
            batch = opportunities[batch_start:batch_start + self._batch_size]
            batch_results = await self._score_single_batch(batch, session, batch_start)
            results.extend(batch_results)

        return results

    async def _score_single_batch(
        self,
        batch: list[dict[str, Any]],
        session: aiohttp.ClientSession,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Оценить один батч через LLM.

        Args:
            batch: батч возможностей.
            session: aiohttp сессия.
            offset: смещение индексов в общем списке.

        Returns:
            Список оценок для батча.
        """
        # Получаем разрешение от rate limiter
        acquired = await self._rate_limiter.acquire(priority="NORMAL", timeout=30.0)
        if not acquired:
            logger.warning("Rate limiter: таймаут ожидания токена, fallback score=50")
            return self._fallback_scores(batch, offset)

        # Если ai_router недоступен - fallback
        if ai_router is None:
            logger.warning("ai_router недоступен, fallback score=50")
            return self._fallback_scores(batch, offset)

        prompt = self._build_prompt(batch)

        try:
            response = await ai_router.call_llm_json(
                session,
                prompt,
                max_output_tokens=1024,
                temperature=0.2,
                timeout=30,
            )

            if isinstance(response, list) and len(response) == len(batch):
                # Корректируем id с учетом offset
                for item in response:
                    if isinstance(item, dict) and "id" in item:
                        item["id"] = item["id"] + offset
                return response

            # Если формат ответа некорректный - fallback
            logger.warning("LLM вернул некорректный формат, fallback score=50")
            return self._fallback_scores(batch, offset)

        except Exception as e:
            logger.warning("Ошибка LLM batch scoring: %s, fallback score=50", e)
            return self._fallback_scores(batch, offset)

    @staticmethod
    def _fallback_scores(
        batch: list[dict[str, Any]], offset: int = 0
    ) -> list[dict[str, Any]]:
        """Возвращает fallback оценки score=50 для всех элементов батча.

        Args:
            batch: батч возможностей.
            offset: смещение индексов.

        Returns:
            Список словарей с дефолтной оценкой.
        """
        return [
            {"id": offset + i, "score": 50, "reasoning": "fallback: LLM unavailable"}
            for i in range(len(batch))
        ]
