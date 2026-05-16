"""Предиктор движения линий (коэффициентов).

Использует LLM для прогнозирования направления и скорости
изменения коэффициентов на основе текущих данных.
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


class LinePredictor:
    """Предсказывает движение линий через LLM-анализ."""

    async def predict(
        self,
        session: aiohttp.ClientSession,
        event_id: str,
        outcome: str,
        current_odds: float,
        velocity: float,
        sport: str,
        time_to_event_min: float,
    ) -> dict[str, Any]:
        """Предсказать движение линии.

        Args:
            session: aiohttp сессия.
            event_id: идентификатор события.
            outcome: исход (название команды/тотал).
            current_odds: текущий коэффициент.
            velocity: скорость изменения (ед/сек).
            sport: вид спорта.
            time_to_event_min: время до начала события в минутах.

        Returns:
            dict с ключами: direction, magnitude, confidence, timeframe_min.
        """
        default: dict[str, Any] = {
            "direction": "stable",
            "magnitude": 0.0,
            "confidence": 0,
            "timeframe_min": 15,
        }

        if ai_router is None:
            logger.debug("ai_router недоступен, возвращаем default")
            return default

        prompt = (
            "Ты - эксперт по движению букмекерских линий. "
            "Проанализируй текущую ситуацию и предскажи направление движения коэффициента.\n\n"
            f"Событие ID: {event_id}\n"
            f"Исход: {outcome}\n"
            f"Текущий коэффициент: {current_odds}\n"
            f"Скорость изменения: {velocity:.6f} ед/сек\n"
            f"Спорт: {sport}\n"
            f"Время до события: {time_to_event_min:.0f} мин\n\n"
            "Учитывай:\n"
            "1. Положительная velocity = коэфф. растет (ставки на обратный исход)\n"
            "2. Близость к старту = более резкие движения\n"
            "3. Тип спорта влияет на волатильность линий\n\n"
            "Ответь строго в формате JSON:\n"
            '{"direction": "up"/"down"/"stable", '
            '"magnitude": <0.0-0.5 - ожидаемое изменение коэфф.>, '
            '"confidence": <0-100>, '
            '"timeframe_min": <5/15/30 - за какое время произойдет>}'
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
            logger.warning("Ошибка вызова LLM в LinePredictor: %s", exc)
            return default

        if resp is None:
            return default

        direction = str(resp.get("direction", "stable"))
        if direction not in ("up", "down", "stable"):
            direction = "stable"

        magnitude = float(resp.get("magnitude", 0.0))
        magnitude = max(0.0, min(0.5, magnitude))

        confidence = int(resp.get("confidence", 0))
        confidence = max(0, min(100, confidence))

        timeframe_min = int(resp.get("timeframe_min", 15))
        if timeframe_min not in (5, 15, 30):
            timeframe_min = 15

        result: dict[str, Any] = {
            "direction": direction,
            "magnitude": magnitude,
            "confidence": confidence,
            "timeframe_min": timeframe_min,
        }
        logger.info(
            "LinePredictor: event=%s direction=%s mag=%.3f conf=%d tf=%dmin",
            event_id, direction, magnitude, confidence, timeframe_min,
        )
        return result


def compute_urgency_factor(prediction: dict[str, Any]) -> float:
    """Вычислить фактор срочности исполнения на основе прогноза.

    Возвращает значение от 1.0 до 2.0:
      - direction='down' и confidence>70 -> 1.5-2.0 (нужно действовать быстро)
      - иначе -> 1.0 (обычный приоритет)
    """
    direction = prediction.get("direction", "stable")
    confidence = int(prediction.get("confidence", 0))

    if direction == "down" and confidence > 70:
        # Линейная интерполяция: confidence 71->1.5, confidence 100->2.0
        factor = 1.5 + (confidence - 70) / 60.0
        return min(2.0, factor)

    return 1.0
