"""LeadScorer: AI-оценка лидов с фриланс-площадок.

Использует ai_router для LLM-анализа заказа (бюджет, срочность, fit).
При ошибке LLM - fallback на эвристический скоринг.
"""

from __future__ import annotations

from typing import Any, Optional

import aiohttp

import ai_router
from freelance_automation.base import Order
from logging_config import get_logger

log = get_logger(__name__)

_SCORING_PROMPT_TEMPLATE = """Analyze the following freelance order and score it from 0 to 100 based on:
- budget (higher budget = higher score)
- urgency (urgent keywords like "ASAP", "срочно", "быстро" = higher score)
- service_fit (web dev, bots, automation, AI = higher score)
- description_quality (detailed, clear requirements = higher score)
- red_flags (unrealistic budget, vague scope, suspicious = lower score)

Order:
Title: {title}
Description: {description}
Budget: {budget}
URL: {url}

Respond in JSON format:
{{"score": <int 0-100>, "factors": {{"budget": <int 0-25>, "urgency": <int 0-25>, "service_fit": <int 0-25>, "description_quality": <int 0-25>}}, "explanation": "<brief reason>"}}"""


_URGENCY_KEYWORDS = [
    "срочно", "asap", "быстро", "сегодня", "urgent", "немедленно",
    "горит", "дедлайн", "deadline",
]

_FIT_KEYWORDS = [
    "бот", "bot", "telegram", "python", "автоматизация", "automation",
    "web", "api", "backend", "парсер", "parser", "ai", "ml",
]


class LeadScorer:
    """Оценщик лидов с AI и эвристическим fallback."""

    async def score_lead(
        self, session: aiohttp.ClientSession, order: Order
    ) -> dict[str, Any]:
        """Оценить заказ. Возвращает {score: int, factors: dict}."""
        result = await self._score_with_llm(session, order)
        if result is not None:
            return result

        log.warning("lead_scoring_llm_fallback", order_id=order.id)
        return self._heuristic_score(order)

    async def _score_with_llm(
        self, session: aiohttp.ClientSession, order: Order
    ) -> Optional[dict[str, Any]]:
        """Попытка оценки через LLM."""
        prompt = _SCORING_PROMPT_TEMPLATE.format(
            title=(order.title or "")[:200],
            description=(order.description or "")[:1000],
            budget=order.budget or "not specified",
            url=order.url,
        )
        try:
            data = await ai_router.call_llm_json(session, prompt)
            if data and "score" in data:
                score = max(0, min(100, int(data["score"])))
                factors = data.get("factors", {})
                return {"score": score, "factors": factors}
        except Exception as e:
            log.error("lead_scoring_llm_error", error=str(e))
        return None

    def _heuristic_score(self, order: Order) -> dict[str, Any]:
        """Эвристический скоринг на основе бюджета и ключевых слов."""
        score = 0
        factors: dict[str, int] = {}

        # Budget factor (0-25)
        budget_score = 0
        if order.budget is not None:
            if order.budget >= 50000:
                budget_score = 25
            elif order.budget >= 20000:
                budget_score = 20
            elif order.budget >= 10000:
                budget_score = 15
            elif order.budget >= 5000:
                budget_score = 10
            else:
                budget_score = 5
        factors["budget"] = budget_score
        score += budget_score

        # Urgency factor (0-25)
        text_lower = f"{order.title} {order.description}".lower()
        urgency_score = 0
        for kw in _URGENCY_KEYWORDS:
            if kw in text_lower:
                urgency_score = min(25, urgency_score + 8)
        factors["urgency"] = urgency_score
        score += urgency_score

        # Service fit factor (0-25)
        fit_score = 0
        for kw in _FIT_KEYWORDS:
            if kw in text_lower:
                fit_score = min(25, fit_score + 5)
        factors["service_fit"] = fit_score
        score += fit_score

        # Description quality (0-25)
        desc_len = len(order.description)
        if desc_len > 500:
            quality_score = 25
        elif desc_len > 200:
            quality_score = 18
        elif desc_len > 50:
            quality_score = 10
        else:
            quality_score = 5
        factors["description_quality"] = quality_score
        score += quality_score

        return {"score": min(100, score), "factors": factors}
