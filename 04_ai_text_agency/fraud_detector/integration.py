"""Integration layer for fraud detection with freelance scheduler."""

from __future__ import annotations

import aiohttp

import config
from fraud_detector.detector import FraudDetector
from freelance_automation.base import Order
from logging_config import get_logger

log = get_logger(__name__)

_detector: FraudDetector | None = None


def _get_detector() -> FraudDetector:
    """Lazy-init singleton detector."""
    global _detector
    if _detector is None:
        _detector = FraudDetector()
    return _detector


async def filter_before_response(session: aiohttp.ClientSession, order: Order) -> bool:
    """Check if an order is safe to respond to.

    Returns:
        True if safe to respond, False if blocked as fraud.
    """
    try:
        detector = _get_detector()
        result = await detector.analyze_order(session, order)
    except Exception:
        # If fraud detection fails, allow the order to proceed
        log.warning("fraud_check_failed", order_id=order.id)
        return True

    threshold = int(getattr(config, "FRAUD_SCORE_THRESHOLD", 70))

    if result["score"] >= threshold:
        log.warning(
            "order_blocked_fraud",
            order_id=order.id,
            order_title=order.title,
            score=result["score"],
            flags=result["flags"],
        )
        return False

    return True
