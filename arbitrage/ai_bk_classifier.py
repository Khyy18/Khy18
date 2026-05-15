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

    async def predict_account_lifetime(
        self,
        session: aiohttp.ClientSession,
        bookmaker: str,
    ) -> dict[str, Any]:
        """Предсказать оставшееся время жизни аккаунта у букмекера.

        На основе: кол-во ставок, частота (ставок/день), win_rate,
        средний stake, время жизни аккаунта.

        Returns:
            dict с ключами: days_remaining, risk_score (0-100), recommendations (list[str])
        """
        default: dict[str, Any] = {
            "days_remaining": 90,
            "risk_score": 30,
            "recommendations": ["Недостаточно данных для прогноза"],
        }

        # Get bookmaker stats
        bk_stats = memory.get_bookmaker_stats(bookmaker)
        account_age = memory.get_account_age_days(bookmaker)
        total_bets = bk_stats.get("total_bets", 0)

        if total_bets < 5:
            return default

        # Calculate frequency
        bets_per_day = total_bets / max(account_age, 1)

        # Calculate win rate
        win_rate = 0.0
        try:
            # Approximate from avg_pnl
            avg_pnl = bk_stats.get("avg_pnl", 0.0)
            win_rate = 0.55 if avg_pnl > 0 else 0.45
        except Exception:
            win_rate = 0.5

        if ai_router is None:
            # Heuristic fallback without LLM
            risk_score = min(100, int(bets_per_day * 15 + (win_rate - 0.5) * 200))
            days_remaining = max(7, 90 - int(bets_per_day * 10))
            recommendations: list[str] = []
            if bets_per_day > 3:
                recommendations.append(f"Снизить частоту с {bets_per_day:.1f} до 2-3 ставок/день")
            if win_rate > 0.6:
                recommendations.append("Высокий винрейт привлекает внимание, добавить мусорные ставки")
            if not recommendations:
                recommendations.append("Текущий паттерн приемлемый")
            return {
                "days_remaining": days_remaining,
                "risk_score": risk_score,
                "recommendations": recommendations,
            }

        prompt = (
            "Ты - эксперт по безопасности аккаунтов у букмекеров. "
            "Оцени оставшееся время жизни аккаунта арбитражника.\n\n"
            f"Букмекер: {bookmaker}\n"
            f"Статистика:\n"
            f"  Всего ставок: {total_bets}\n"
            f"  Частота: {bets_per_day:.2f} ставок/день\n"
            f"  Win rate: {win_rate:.1%}\n"
            f"  Средний PnL/ставку: {bk_stats.get('avg_pnl', 0):.4f}\n"
            f"  Возраст аккаунта: {account_age} дней\n"
            f"  Trap rate: {bk_stats.get('trap_rate', 0):.1f}%\n\n"
            "Ответь JSON:\n"
            '{"days_remaining": <7-180>, "risk_score": <0-100>, '
            '"recommendations": ["рекомендация 1", "рекомендация 2"]}'
        )

        try:
            resp = await ai_router.call_llm_json(
                session, prompt, max_output_tokens=256, temperature=0.2, timeout=25
            )
        except Exception as exc:
            logger.warning("predict_account_lifetime LLM ошибка: %s", exc)
            return default

        if resp is None:
            return default

        days_remaining = int(resp.get("days_remaining", 90))
        days_remaining = max(7, min(180, days_remaining))
        risk_score = int(resp.get("risk_score", 30))
        risk_score = max(0, min(100, risk_score))
        recommendations = resp.get("recommendations", [])
        if not isinstance(recommendations, list):
            recommendations = [str(recommendations)]

        logger.info(
            "[BK_CLASSIFIER] Прогноз %s: осталось %d дней, риск %d/100",
            bookmaker, days_remaining, risk_score,
        )
        return {
            "days_remaining": days_remaining,
            "risk_score": risk_score,
            "recommendations": recommendations,
        }


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
