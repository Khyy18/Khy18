"""Модуль расчёта ставок и самообучения AI-фильтра.

SettlementEngine:
  - settle_bets: расчёт PENDING/SIMULATED ставок (WON/LOST на основе implied probability)
  - learn: анализ 7 дней данных, генерация правил через LLM, сохранение в БД
"""

from __future__ import annotations

import os
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

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


class SettlementEngine:
    """Движок расчёта ставок и самообучения."""

    def __init__(self) -> None:
        pass

    async def settle_bets(self, session: aiohttp.ClientSession) -> None:
        """Расчёт PENDING/SIMULATED ставок старше 3 часов.

        Для DRY_RUN/SIMULATED ставок: результат определяется случайно
        с вероятностью, равной implied probability (1/odds).
        Обновляет bets.result и bets.pnl, агрегирует daily PnL.
        """
        pending = memory.get_pending_bets_for_settlement()
        if not pending:
            return

        print(f"[SETTLEMENT] Расчёт {len(pending)} ставок")

        # Агрегация PnL по дням
        daily_agg: dict[str, dict[str, float]] = defaultdict(
            lambda: {"staked": 0.0, "won": 0.0, "pnl": 0.0}
        )

        for bet in pending:
            bet_id: int = bet["id"]
            odds: float = bet.get("odds", 0.0)
            stake: float = bet.get("stake", 0.0)
            ts_str: str = bet.get("ts", "")

            # Определяем дату ставки
            try:
                bet_date = ts_str[:10]  # YYYY-MM-DD
            except (IndexError, TypeError):
                bet_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            if odds <= 1.0:
                # Невалидные коэффициенты - VOID
                memory.update_bet_result(bet_id, "VOID", 0.0)
                continue

            # Implied probability = 1 / odds
            implied_prob: float = 1.0 / odds

            # Симуляция результата
            if random.random() < implied_prob:
                # WON: выигрыш = stake * (odds - 1)
                pnl = stake * (odds - 1.0)
                result = "WON"
            else:
                # LOST: проигрыш = -stake
                pnl = -stake
                result = "LOST"

            memory.update_bet_result(bet_id, result, pnl)

            # Агрегация
            daily_agg[bet_date]["staked"] += stake
            if result == "WON":
                daily_agg[bet_date]["won"] += stake * odds
            daily_agg[bet_date]["pnl"] += pnl

        # Обновляем daily_pnl
        for date_str, agg in daily_agg.items():
            staked = agg["staked"]
            roi = (agg["pnl"] / staked * 100.0) if staked > 0 else 0.0
            memory.update_daily_pnl(date_str, staked, agg["won"], agg["pnl"], roi)

        print(f"[SETTLEMENT] Расчёт завершён. Дней обновлено: {len(daily_agg)}")

    async def learn(self, session: aiohttp.ClientSession) -> None:
        """Самообучение: анализ 7 дней данных и генерация правил через LLM.

        Анализирует:
          - букмекеры с высоким % отмен/проигрышей
          - наиболее прибыльные типы арбитража
          - рабочие пороги profit_pct
        Вызывает LLM для генерации правил, сохраняет в ai_learnings.
        """
        if ai_router is None:
            print("[SETTLEMENT] ai_router недоступен, обучение пропущено")
            return

        # Получаем данные за 7 дней
        daily_data = memory.get_daily_pnl(days=7)
        recent_bets = memory.get_recent_bets(limit=200)

        if not recent_bets:
            print("[SETTLEMENT] Нет данных для обучения")
            return

        # Анализ по букмекерам
        bm_stats: dict[str, dict[str, Any]] = {}
        for bet in recent_bets:
            bm = bet.get("bookmaker", "unknown")
            if bm not in bm_stats:
                bm_stats[bm] = {"total": 0, "won": 0, "lost": 0, "void": 0, "pnl": 0.0}
            bm_stats[bm]["total"] += 1
            result = bet.get("result", "")
            if result == "WON":
                bm_stats[bm]["won"] += 1
            elif result == "LOST":
                bm_stats[bm]["lost"] += 1
            elif result == "VOID":
                bm_stats[bm]["void"] += 1
            bm_stats[bm]["pnl"] += float(bet.get("pnl", 0.0) or 0.0)

        # Формируем промпт для LLM
        prompt = (
            "Ты - эксперт по спортивному арбитражу. "
            "Проанализируй данные за 7 дней и сгенерируй правила для AI-фильтра.\n\n"
            f"Статистика по букмекерам:\n{_format_bm_stats(bm_stats)}\n\n"
            f"Daily PnL (последние 7 дней): {daily_data}\n\n"
            "Сгенерируй JSON-список правил. Каждое правило:\n"
            '{"rule_type": "bookmaker_risk|arb_type_preference|profit_threshold", '
            '"rule_text": "<описание правила на русском>", '
            '"confidence": <0.0-1.0>}\n\n'
            "Ответь строго в формате JSON-массива правил (3-5 правил)."
        )

        try:
            resp = await ai_router.call_llm_json(
                session,
                prompt,
                max_output_tokens=512,
                temperature=0.3,
                timeout=30,
            )
        except Exception as exc:
            print(f"[SETTLEMENT] Ошибка вызова LLM для обучения: {exc}")
            return

        if resp is None:
            print("[SETTLEMENT] LLM не вернул ответ для обучения")
            return

        # Парсим правила
        rules: list[dict[str, Any]] = []
        if isinstance(resp, list):
            rules = resp
        elif isinstance(resp, dict) and "rules" in resp:
            rules = resp["rules"]
        elif isinstance(resp, dict):
            rules = [resp]

        saved = 0
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            rule_type = str(rule.get("rule_type", "general"))
            rule_text = str(rule.get("rule_text", ""))
            confidence = float(rule.get("confidence", 0.5))
            if rule_text:
                memory.save_ai_learning(rule_type, rule_text, confidence, "llm_learn")
                saved += 1

        print(f"[SETTLEMENT] Обучение завершено. Сохранено правил: {saved}")


def _format_bm_stats(bm_stats: dict[str, dict[str, Any]]) -> str:
    """Форматирует статистику букмекеров для промпта."""
    lines: list[str] = []
    for bm, st in bm_stats.items():
        total = st["total"]
        win_rate = (st["won"] / total * 100.0) if total > 0 else 0.0
        void_rate = (st["void"] / total * 100.0) if total > 0 else 0.0
        lines.append(
            f"  {bm}: ставок={total}, win_rate={win_rate:.1f}%, "
            f"void_rate={void_rate:.1f}%, pnl={st['pnl']:.2f}"
        )
    return "\n".join(lines) if lines else "  нет данных"
