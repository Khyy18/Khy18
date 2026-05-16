"""Стратегия вывода средств.

Использует LLM для рекомендаций по выводу средств
с букмекерских аккаунтов на основе рисков и балансов.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

import aiohttp

from arbitrage import memory

# Импорт ai_router из корневого проекта
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)
try:
    import ai_router
except ImportError:
    ai_router = None  # type: ignore

logger = logging.getLogger(__name__)


class WithdrawalStrategy:
    """Стратегия вывода средств на основе AI-анализа рисков."""

    async def recommend(self, session: aiohttp.ClientSession) -> list[dict[str, Any]]:
        """Рекомендовать вывод средств с букмекерских аккаунтов.

        Анализирует балансы, классификации рисков и историю ставок
        для формирования рекомендаций по выводу.

        Returns:
            Список словарей с ключами: bookmaker, amount, reason, urgency.
        """
        if ai_router is None:
            logger.debug("ai_router недоступен, рекомендации по выводу невозможны")
            return []

        # Получаем данные
        balances = memory.get_all_account_balances()
        classifications = memory.get_all_bk_classifications()

        if not balances and not classifications:
            logger.debug("Нет данных о балансах и классификациях")
            return []

        # Формируем сводку для LLM
        balances_text = ""
        if balances:
            for b in balances:
                balances_text += (
                    f"  {b.get('bookmaker', '?')}: "
                    f"баланс={b.get('balance', 0):.2f}, "
                    f"обновлено={b.get('last_updated', '?')}\n"
                )

        classifications_text = ""
        if classifications:
            for c in classifications:
                classifications_text += (
                    f"  {c.get('bookmaker', '?')}: "
                    f"риск={c.get('risk_level', '?')}, "
                    f"дней_до_среза={c.get('days_to_cut', '?')}, "
                    f"рекомендация={c.get('recommendation', '?')}\n"
                )

        prompt = (
            "Ты - эксперт по управлению банкроллом в арбитражных ставках. "
            "Рекомендуй вывод средств с букмекерских аккаунтов.\n\n"
            f"Балансы:\n{balances_text}\n"
            f"Классификации рисков:\n{classifications_text}\n"
            "Правила:\n"
            "1. С высокорисковых букмекеров выводить больше\n"
            "2. Critical - вывести максимум как можно скорее\n"
            "3. Оставлять минимум для продолжения работы (если risk не critical)\n"
            "4. Учитывать минимальные суммы вывода (обычно 10-50)\n\n"
            "Ответь строго в формате JSON:\n"
            '{"withdrawals": [{"bookmaker": "<имя>", "amount": <сумма>, '
            '"reason": "<причина на русском>", '
            '"urgency": "low"/"medium"/"high"}]}\n\n'
            "Если вывод не требуется, ответь:\n"
            '{"withdrawals": []}'
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
            logger.warning("Ошибка LLM в WithdrawalStrategy: %s", exc)
            return []

        if resp is None:
            return []

        raw_withdrawals = resp.get("withdrawals", [])
        if not isinstance(raw_withdrawals, list):
            return []

        results: list[dict[str, Any]] = []
        for w in raw_withdrawals:
            if not isinstance(w, dict):
                continue

            bookmaker = str(w.get("bookmaker", ""))
            if not bookmaker:
                continue

            amount = float(w.get("amount", 0.0))
            if amount <= 0:
                continue

            reason = str(w.get("reason", ""))
            urgency = str(w.get("urgency", "low"))
            if urgency not in ("low", "medium", "high"):
                urgency = "low"

            results.append({
                "bookmaker": bookmaker,
                "amount": amount,
                "reason": reason,
                "urgency": urgency,
            })

        logger.info("WithdrawalStrategy: %d рекомендаций по выводу", len(results))
        return results
