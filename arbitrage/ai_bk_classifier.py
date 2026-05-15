"""Классификатор букмекеров по уровню риска.

Использует LLM для оценки риска работы с букмекером
на основе истории ставок, процента отмен и trap rate.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Optional

import aiohttp

from arbitrage import config, memory

# Импорт ai_router из корневого проекта
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)
try:
    import ai_router
except ImportError:
    ai_router = None  # type: ignore

logger = logging.getLogger(__name__)


class BookmakerClassifier:
    """Классификатор букмекеров через LLM-анализ истории."""

    async def classify(
        self,
        session: aiohttp.ClientSession,
        bookmaker: str,
    ) -> dict[str, Any]:
        """Классифицировать букмекера по уровню риска.

        Args:
            session: aiohttp сессия.
            bookmaker: название букмекера.

        Returns:
            dict с ключами: risk_level, days_to_cut, recommendation.
        """
        default: dict[str, Any] = {
            "risk_level": "medium",
            "days_to_cut": 60,
            "recommendation": "Недостаточно данных для классификации",
        }

        if ai_router is None:
            logger.debug("ai_router недоступен, возвращаем default для %s", bookmaker)
            return default

        # Получаем статистику букмекера
        bk_stats = memory.get_bookmaker_stats(bookmaker)

        prompt = (
            "Ты - эксперт по оценке букмекеров для арбитражных ставок. "
            "Классифицируй букмекера по уровню риска для арбитражника.\n\n"
            f"Букмекер: {bookmaker}\n"
            f"Статистика:\n"
            f"  Всего ставок: {bk_stats.get('total_bets', 0)}\n"
            f"  Процент отмен (void): {bk_stats.get('cancelled_pct', 0):.1f}%\n"
            f"  Средний PnL: {bk_stats.get('avg_pnl', 0):.4f}\n"
            f"  Trap rate (surebets lost): {bk_stats.get('trap_rate', 0):.1f}%\n\n"
            "Уровни риска:\n"
            "  low - безопасный букмекер, можно работать активно\n"
            "  medium - умеренный риск, стандартная осторожность\n"
            "  high - высокий риск ограничений/блокировки\n"
            "  critical - очень опасно, рекомендуется вывод средств\n\n"
            "Ответь строго в формате JSON:\n"
            '{"risk_level": "low"/"medium"/"high"/"critical", '
            '"days_to_cut": <15-90 дней до вероятного ограничения>, '
            '"recommendation": "<рекомендация на русском>"}'
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
            logger.warning("Ошибка LLM в BookmakerClassifier: %s", exc)
            return default

        if resp is None:
            return default

        risk_level = str(resp.get("risk_level", "medium"))
        if risk_level not in ("low", "medium", "high", "critical"):
            risk_level = "medium"

        days_to_cut = int(resp.get("days_to_cut", 60))
        days_to_cut = max(15, min(90, days_to_cut))

        recommendation = str(resp.get("recommendation", "нет рекомендации"))

        # Сохраняем классификацию в БД
        memory.save_bk_classification(bookmaker, risk_level, days_to_cut, recommendation)

        result: dict[str, Any] = {
            "risk_level": risk_level,
            "days_to_cut": days_to_cut,
            "recommendation": recommendation,
        }
        logger.info(
            "BookmakerClassifier: %s -> risk=%s days_to_cut=%d",
            bookmaker, risk_level, days_to_cut,
        )
        return result


async def classifier_loop(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
    """Фоновый цикл классификации букмекеров (раз в сутки).

    Классифицирует всех букмекеров из config.BOOKMAKERS.
    """
    classifier = BookmakerClassifier()
    interval = 86400  # 24 часа

    while True:
        try:
            for bm in config.BOOKMAKERS:
                result = await classifier.classify(session, bm)
                state.setdefault("bk_classifications", {})[bm] = result
            logger.info("classifier_loop: классификация %d букмекеров завершена", len(config.BOOKMAKERS))
        except Exception as exc:
            logger.error("classifier_loop ошибка: %s", exc)

        await asyncio.sleep(interval)
