"""Интеграция Lead Scoring с FreelanceScheduler.

auto_score_new_order() вызывается при обнаружении новых заказов.
"""

from __future__ import annotations

import aiohttp

import config
from freelance_automation.base import Order
from lead_scoring.models import init_db, save_score
from lead_scoring.scorer import LeadScorer
from logging_config import get_logger

log = get_logger(__name__)

_scorer = LeadScorer()


async def auto_score_new_order(
    session: aiohttp.ClientSession, order: Order
) -> int:
    """Оценить новый заказ и сохранить результат.

    Если оценка выше порога LEAD_SCORE_AUTO_RESPOND_THRESHOLD,
    помечает заказ для авто-ответа.

    Returns:
        Оценка лида (0-100).
    """
    init_db()

    result = await _scorer.score_lead(session, order)
    score = result["score"]
    factors = result["factors"]

    save_score(
        order_id=order.id,
        tg_id=0,
        score=score,
        factors=factors,
    )

    threshold = config.LEAD_SCORE_AUTO_RESPOND_THRESHOLD
    if score >= threshold:
        log.info(
            "lead_above_threshold",
            order_id=order.id,
            score=score,
            threshold=threshold,
        )

    return score
