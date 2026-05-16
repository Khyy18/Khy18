"""AI-аллокатор банкролла: Kelly criterion + LLM-коррекция.

Рассчитывает оптимальные ставки на основе критерия Келли
с консервативным половинным Келли и AI-корректировкой рисков.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Optional

import aiohttp

from arbitrage.dynamic_kelly import DynamicKelly

logger = logging.getLogger(__name__)

# Импорт ai_router из корневого проекта
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)
try:
    import ai_router
except ImportError:
    ai_router = None  # type: ignore

from arbitrage import config, memory


# Максимальная доля банкролла на одну ставку (%)
MAX_BET_PCT: float = config.MAX_BET_PCT


def kelly_fraction(odds: float, win_prob: float) -> float:
    """Рассчитать оптимальную долю банкролла по критерию Келли.

    f* = (b*p - q) / b
    где b = odds - 1, p = win_prob, q = 1 - p

    Результат зажат в диапазоне [0, 1].
    """
    b = odds - 1.0
    if b <= 0:
        return 0.0
    p = win_prob
    q = 1.0 - p
    f_star = (b * p - q) / b
    return max(0.0, min(1.0, f_star))


class BankrollAllocator:
    """Распределение банкролла с Kelly criterion и AI-коррекцией."""

    def __init__(self, session: aiohttp.ClientSession, bankroll: float = 1000.0) -> None:
        self._session = session
        self._bankroll = bankroll
        self._dynamic_kelly = DynamicKelly()

    async def allocate(
        self,
        opportunities: list[dict[str, Any]],
        bankroll: float,
    ) -> list[dict[str, Any]]:
        """Рассчитать оптимальные ставки для списка возможностей.

        Для каждой возможности:
          1. Рассчитать Kelly fraction
          2. Применить half-Kelly (консервативно)
          3. Ограничить MAX_BET_PCT
          4. Запросить AI-коррекцию

        Возвращает список dict:
          {opportunity, stake_amount, kelly_fraction, ai_adjustment_reason}
        """
        if not opportunities:
            return []

        allocations: list[dict[str, Any]] = []
        max_stake = bankroll * (MAX_BET_PCT / 100.0)

        for opp in opportunities:
            sizing_mode = opp.get("sizing_mode", "kelly")

            if sizing_mode == "surebet":
                # Fix 1: Surebets - размер по profit_pct, не Kelly
                profit_pct = float(opp.get("profit_pct", 0.0))
                stake = bankroll * (MAX_BET_PCT / 100.0) * min(profit_pct / 10.0, 1.0)
                kf = 0.0  # Kelly не применяется

                # Рассчитываем ставки на каждую ногу пропорционально обратным коэфф.
                odds_list = opp.get("odds", [])
                bookmakers_list = opp.get("bookmakers", [])
                outcome_names = opp.get("details", {}).get("outcomes", [])
                if not outcome_names:
                    outcome_names = [f"Outcome {i+1}" for i in range(len(odds_list))]
            else:
                # Value bets - стандартный Kelly
                odds = float(opp.get("best_odds", opp.get("odds", 2.0)))
                win_prob = float(opp.get("win_prob", opp.get("implied_prob", 0.5)))

                kf = kelly_fraction(odds, win_prob)
                # Half-Kelly для консервативности
                half_kelly = kf / 2.0
                stake = bankroll * half_kelly

            # Ограничение максимальной ставки
            stake = min(stake, max_stake)

            alloc_entry: dict[str, Any] = {
                "opportunity": opp,
                "stake_amount": round(stake, 2),
                "kelly_fraction": round(kf, 4),
                "ai_adjustment_reason": "",
            }

            # Для surebets добавляем список ног с пропорциональными ставками
            if sizing_mode == "surebet" and odds_list:
                inv_sum = sum(1.0 / o for o in odds_list if o > 0)
                if inv_sum > 0:
                    legs: list[dict[str, Any]] = []
                    for idx, o in enumerate(odds_list):
                        if o <= 0:
                            continue
                        leg_stake = stake * (1.0 / o) / inv_sum
                        bm = bookmakers_list[idx] if idx < len(bookmakers_list) else "unknown"
                        outcome = outcome_names[idx] if idx < len(outcome_names) else f"Outcome {idx+1}"
                        legs.append({
                            "bookmaker": bm,
                            "outcome": outcome,
                            "odds": o,
                            "stake": round(leg_stake, 2),
                        })
                    alloc_entry["legs"] = legs

            allocations.append(alloc_entry)

        # Dynamic Kelly reduction
        kelly_state = self._build_kelly_state(bankroll)
        reduction_factor = self._dynamic_kelly.get_reduction_factor(kelly_state)
        if reduction_factor < 1.0:
            for alloc in allocations:
                alloc["stake_amount"] = round(alloc["stake_amount"] * reduction_factor, 2)
            logger.info("[AI_ALLOCATOR] Kelly reduction factor: %.3f", reduction_factor)

        # AI-коррекция портфеля
        ai_adjustments = await self._get_ai_adjustments(allocations, bankroll)
        if ai_adjustments:
            for i, alloc in enumerate(allocations):
                adj = ai_adjustments.get(str(i))
                if adj:
                    factor = float(adj.get("factor", 1.0))
                    reason = str(adj.get("reason", ""))
                    alloc["stake_amount"] = round(alloc["stake_amount"] * factor, 2)
                    # Повторно ограничить после корректировки
                    alloc["stake_amount"] = min(alloc["stake_amount"], max_stake)
                    alloc["ai_adjustment_reason"] = reason

        return allocations

    async def _get_ai_adjustments(
        self,
        allocations: list[dict[str, Any]],
        bankroll: float,
    ) -> Optional[dict[str, Any]]:
        """Запросить AI-коррекцию распределения ставок."""
        total_exposure = sum(a["stake_amount"] for a in allocations)
        exposure_pct = (total_exposure / bankroll * 100.0) if bankroll > 0 else 0.0

        portfolio_summary = []
        for i, alloc in enumerate(allocations):
            opp = alloc["opportunity"]
            portfolio_summary.append({
                "index": i,
                "event": opp.get("event", "неизвестно"),
                "sport": opp.get("sport", "неизвестно"),
                "stake": alloc["stake_amount"],
                "kelly": alloc["kelly_fraction"],
                "odds": opp.get("best_odds", opp.get("odds", 0)),
            })

        prompt = (
            "Ты - риск-менеджер спортивного арбитража. "
            "Проанализируй портфель ставок и предложи корректировки.\n\n"
            f"Банкролл: {bankroll:.2f}\n"
            f"Общая экспозиция: {total_exposure:.2f} ({exposure_pct:.1f}%)\n"
            f"Максимум на ставку: {MAX_BET_PCT}%\n\n"
            f"Позиции:\n{portfolio_summary}\n\n"
            "Учитывай:\n"
            "- Диверсификация по видам спорта\n"
            "- Коррелированные события (один и тот же матч)\n"
            "- Общий риск портфеля\n"
            "- Снижение ставки при высокой неопределённости\n\n"
            "Ответь в формате JSON:\n"
            '{"0": {"factor": 1.0, "reason": ""}, "1": {"factor": 0.8, "reason": "..."}, ...}\n'
            "factor - множитель к текущей ставке (0.5-1.5). "
            "Если корректировка не нужна - factor=1.0, reason пустая строка."
        )

        try:
            if ai_router is None:
                return None
            resp = await ai_router.call_llm_json(
                self._session,
                prompt,
                max_output_tokens=256,
                temperature=0.2,
                timeout=20,
            )
            return resp
        except Exception as exc:
            print(f"[AI_ALLOCATOR] Ошибка AI-коррекции: {exc}")
            return None

    def _build_kelly_state(self, bankroll: float) -> dict[str, Any]:
        """Build state dict for DynamicKelly from recent bets."""
        recent = memory.get_recent_bets(50)
        pnls = [float(b.get("pnl") or 0.0) for b in recent if b.get("pnl") is not None]

        # pnls are newest-first from get_recent_bets; reverse to get chronological order
        chronological_pnls = list(reversed(pnls))
        # Reconstruct the starting bankroll before these bets happened
        starting_bankroll = bankroll - sum(chronological_pnls)
        running = starting_bankroll
        hwm = starting_bankroll
        for p in chronological_pnls:
            running += p
            hwm = max(hwm, running)
        # hwm is now the actual peak; bankroll is current position

        # Count losing streak (from most recent)
        losing_streak = 0
        for p in pnls:
            if p < 0:
                losing_streak += 1
            else:
                break

        return {
            "hwm": hwm,
            "current_bankroll": bankroll,
            "recent_pnls": pnls,
            "losing_streak": losing_streak,
        }
