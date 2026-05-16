"""Детектор аномалий в коэффициентах.

Использует LLM для определения, является ли высокоприбыльная
возможность реальной или это ошибка/ловушка букмекера.
"""

from __future__ import annotations

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


class OddsAnomalyDetector:
    """Детектор аномалий в букмекерских коэффициентах."""

    async def detect(
        self,
        session: aiohttp.ClientSession,
        opportunity: dict[str, Any],
    ) -> dict[str, Any]:
        """Определить, является ли возможность аномалией.

        Анализ запускается только при profit_pct > 5.0 (подозрительно высокая прибыль).

        Args:
            session: aiohttp сессия.
            opportunity: словарь с данными арбитражной возможности.

        Returns:
            dict с ключами: is_anomaly, anomaly_type, confidence.
        """
        default: dict[str, Any] = {
            "is_anomaly": False,
            "anomaly_type": "none",
            "confidence": 0,
        }

        profit_pct = float(opportunity.get("profit_pct", 0.0))

        # Если прибыль не подозрительная, аномалии нет
        if profit_pct <= 5.0:
            return default

        if ai_router is None:
            logger.debug("ai_router недоступен, аномалия не проверена")
            return default

        # Подготавливаем данные для LLM
        sport = opportunity.get("sport", "неизвестно")
        event = opportunity.get("event", "неизвестно")
        bookmakers = opportunity.get("bookmakers", [])
        odds = opportunity.get("odds", {})

        prompt = (
            "Ты - эксперт по обнаружению аномалий в букмекерских линиях. "
            "Определи, является ли данная возможность реальной или аномалией.\n\n"
            f"Спорт: {sport}\n"
            f"Событие: {event}\n"
            f"Букмекеры: {bookmakers}\n"
            f"Коэффициенты: {odds}\n"
            f"Прибыль: {profit_pct:.2f}%\n\n"
            "Типы аномалий:\n"
            "  pricing_error - ошибка букмекера в коэффициенте\n"
            "  line_movement - устаревшая линия, скоро скорректируют\n"
            "  insider - подозрение на инсайдерскую информацию\n"
            "  none - легитимная возможность\n\n"
            "Учитывай:\n"
            "1. Прибыль > 5% - подозрительно для большинства рынков\n"
            "2. Если один букмекер сильно отличается от остальных - вероятно ошибка\n"
            "3. Матчи низших лиг чаще имеют ошибки в линиях\n\n"
            "Ответь строго в формате JSON:\n"
            '{"is_anomaly": true/false, '
            '"anomaly_type": "pricing_error"/"line_movement"/"insider"/"none", '
            '"confidence": <0-100>}'
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
            logger.warning("Ошибка LLM в OddsAnomalyDetector: %s", exc)
            return default

        if resp is None:
            return default

        is_anomaly = bool(resp.get("is_anomaly", False))
        anomaly_type = str(resp.get("anomaly_type", "none"))
        if anomaly_type not in ("pricing_error", "line_movement", "insider", "none"):
            anomaly_type = "none"

        confidence = int(resp.get("confidence", 0))
        confidence = max(0, min(100, confidence))

        result: dict[str, Any] = {
            "is_anomaly": is_anomaly,
            "anomaly_type": anomaly_type,
            "confidence": confidence,
        }
        logger.info(
            "OddsAnomalyDetector: event=%s anomaly=%s type=%s conf=%d",
            event, is_anomaly, anomaly_type, confidence,
        )
        return result
