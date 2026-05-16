"""AI-powered fraud detector for freelance orders."""

from __future__ import annotations

import re
from typing import Optional

import aiohttp

import ai_router
from fraud_detector.models import init_db, save_fraud_score
from freelance_automation.base import Order
from logging_config import get_logger

log = get_logger(__name__)

# Patterns for rule-based heuristic
_PHONE_RE = re.compile(r"(\+?\d[\d\-\s]{8,}\d)")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_URGENCY_WORDS = [
    "срочно", "urgent", "asap", "немедленно", "сегодня", "прямо сейчас",
    "через час", "за час", "быстро нужно",
]


class FraudDetector:
    """Detector that analyzes freelance orders for fraud indicators."""

    def __init__(self) -> None:
        init_db()

    async def analyze_order(self, session: aiohttp.ClientSession, order: Order) -> dict:
        """Analyze an order for fraud.

        Returns:
            dict with {score: int (0-100), flags: list[str], is_suspicious: bool}
        """
        # Try LLM-based analysis first
        result = await self._llm_analyze(session, order)

        if result is None:
            # Fallback to rule-based heuristic
            result = self._heuristic_analyze(order)

        # Persist score
        save_fraud_score(order.id, result["score"], result["flags"])

        log.info(
            "fraud_analysis_complete",
            order_id=order.id,
            score=result["score"],
            is_suspicious=result["is_suspicious"],
        )
        return result

    async def _llm_analyze(
        self, session: aiohttp.ClientSession, order: Order
    ) -> Optional[dict]:
        """Use LLM to analyze order for fraud."""
        budget_str = str(order.budget) if order.budget else "не указан"
        prompt = (
            f"Analyze this freelance job posting for fraud indicators:\n"
            f"Title: {order.title}\n"
            f"Description: {order.description}\n"
            f"Budget: {budget_str}\n\n"
            f"Check for: unrealistic budgets, vague descriptions, "
            f"contact info in description (bypassing platform), "
            f"urgency pressure, too-good-to-be-true offers, known scam patterns.\n\n"
            f"Return JSON: {{\"score\": 0-100, \"flags\": [list of red flags found]}}"
        )

        data = await ai_router.call_llm_json(session, prompt)
        if not data:
            return None

        try:
            score = int(data.get("score", 0))
            score = max(0, min(100, score))
            flags = data.get("flags", [])
            if not isinstance(flags, list):
                flags = []
            flags = [str(f) for f in flags]
        except (ValueError, TypeError):
            return None

        return {
            "score": score,
            "flags": flags,
            "is_suspicious": score >= 70,
        }

    def _heuristic_analyze(self, order: Order) -> dict:
        """Rule-based fallback fraud detection."""
        score = 0
        flags: list[str] = []
        text = f"{order.title} {order.description}".lower()

        # Check for contact info in description (bypassing platform)
        if _PHONE_RE.search(order.description):
            score += 25
            flags.append("phone_number_in_description")

        if _EMAIL_RE.search(order.description):
            score += 25
            flags.append("email_in_description")

        # Budget too low for complex work
        if order.budget is not None and order.budget < 100:
            desc_words = len(order.description.split())
            if desc_words > 50:
                score += 20
                flags.append("budget_too_low_for_complex_work")

        # Urgency pressure
        for word in _URGENCY_WORDS:
            if word in text:
                score += 15
                flags.append(f"urgency_pressure: {word}")
                break

        # Vague description (too short)
        if len(order.description.strip()) < 20:
            score += 10
            flags.append("vague_description")

        score = min(score, 100)

        return {
            "score": score,
            "flags": flags,
            "is_suspicious": score >= 70,
        }
