"""Оптимизатор пороговых значений арбитража.

Использует LLM для анализа исторических данных и рекомендации
оптимальных пороговых значений (min profit, min edge, scan interval).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Any, Optional

import aiohttp

from arbitrage import config, memory, telegram_bot

# Импорт ai_router из корневого проекта
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)
try:
    import ai_router
except ImportError:
    ai_router = None  # type: ignore

logger = logging.getLogger(__name__)

# Интервал оптимизации: 7 дней в секундах
_OPTIMIZE_INTERVAL_SEC: int = 7 * 24 * 3600


class ThresholdOptimizer:
    """Оптимизатор пороговых значений через LLM-анализ исторических данных."""

    async def optimize(self, session: aiohttp.ClientSession) -> dict[str, Any]:
        """Проанализировать историю и рекомендовать оптимальные пороги.

        Returns:
            dict с ключами: min_arb_profit, min_value_edge, scan_interval, reasoning.
        """
        default: dict[str, Any] = {
            "min_arb_profit": config.MIN_ARB_PROFIT,
            "min_value_edge": config.MIN_VALUE_EDGE,
            "scan_interval": config.SCAN_INTERVAL_SEC,
            "reasoning": "Оптимизация недоступна",
        }

        if ai_router is None:
            logger.debug("ai_router недоступен, пороги не изменены")
            return default

        # Собираем исторические данные
        stats = memory.get_stats()
        daily_pnl = memory.get_daily_pnl(30)
        learnings = memory.get_ai_learnings(20)

        # Формируем сводку для LLM
        pnl_summary = ""
        if daily_pnl:
            total_pnl = sum(d.get("pnl", 0.0) for d in daily_pnl)
            avg_roi = sum(d.get("roi_pct", 0.0) for d in daily_pnl) / len(daily_pnl)
            pnl_summary = (
                f"PnL за 30 дней: {total_pnl:.2f}, средний ROI: {avg_roi:.2f}%, "
                f"дней с данными: {len(daily_pnl)}"
            )

        learnings_text = ""
        if learnings:
            learnings_text = "\n".join(
                f"  - [{l.get('rule_type', '')}] {l.get('rule_text', '')}"
                for l in learnings[:10]
            )

        prompt = (
            "Ты - эксперт по оптимизации стратегий спортивного арбитража. "
            "На основе исторических данных рекомендуй оптимальные пороги.\n\n"
            f"Текущие настройки:\n"
            f"  min_arb_profit: {config.MIN_ARB_PROFIT}%\n"
            f"  min_value_edge: {config.MIN_VALUE_EDGE}%\n"
            f"  scan_interval: {config.SCAN_INTERVAL_SEC} сек\n\n"
            f"Статистика:\n"
            f"  Всего арбитражей: {stats.get('total_arbs', 0)}\n"
            f"  Исполнено: {stats.get('executed_arbs', 0)}\n"
            f"  Ставок: {stats.get('total_bets', 0)}\n"
            f"  Выиграно: {stats.get('won_bets', 0)}\n"
            f"  Проиграно: {stats.get('lost_bets', 0)}\n"
            f"  Итого PnL: {stats.get('total_pnl', 0.0):.2f}\n\n"
            f"PnL (30 дней): {pnl_summary}\n\n"
        )

        if learnings_text:
            prompt += f"Выученные правила:\n{learnings_text}\n\n"

        prompt += (
            "Рекомендуй новые значения с обоснованием. "
            "Пределы: min_arb_profit [0.5, 5.0], min_value_edge [1.0, 10.0], "
            "scan_interval [15, 120].\n\n"
            "Ответь строго в формате JSON:\n"
            '{"min_arb_profit": <float>, "min_value_edge": <float>, '
            '"scan_interval": <int>, "reasoning": "<обоснование на русском>"}'
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
            logger.warning("Ошибка LLM в ThresholdOptimizer: %s", exc)
            return default

        if resp is None:
            return default

        # Извлекаем и применяем ограничения безопасности
        min_arb_profit = float(resp.get("min_arb_profit", config.MIN_ARB_PROFIT))
        min_arb_profit = max(0.5, min(5.0, min_arb_profit))

        min_value_edge = float(resp.get("min_value_edge", config.MIN_VALUE_EDGE))
        min_value_edge = max(1.0, min(10.0, min_value_edge))

        scan_interval = int(resp.get("scan_interval", config.SCAN_INTERVAL_SEC))
        scan_interval = max(15, min(120, scan_interval))

        reasoning = str(resp.get("reasoning", "нет обоснования"))

        # Применяем новые значения к конфигу
        config.MIN_ARB_PROFIT = min_arb_profit
        config.MIN_VALUE_EDGE = min_value_edge
        config.SCAN_INTERVAL_SEC = scan_interval

        # Сохраняем решение в AI learnings
        memory.save_ai_learning(
            rule_type="threshold_optimization",
            rule_text=(
                f"min_arb_profit={min_arb_profit:.2f}%, "
                f"min_value_edge={min_value_edge:.2f}%, "
                f"scan_interval={scan_interval}s. {reasoning}"
            ),
            confidence=0.8,
            source="ai_optimizer",
        )

        result: dict[str, Any] = {
            "min_arb_profit": min_arb_profit,
            "min_value_edge": min_value_edge,
            "scan_interval": scan_interval,
            "reasoning": reasoning,
        }
        logger.info(
            "ThresholdOptimizer: profit=%.2f%% edge=%.2f%% interval=%ds",
            min_arb_profit, min_value_edge, scan_interval,
        )
        return result

    async def smart_sport_selection(self, session: aiohttp.ClientSession) -> dict[str, Any]:
        """AI-анализ: какие лиги приносят больше всего арбов, какие пусты.

        Ограничения: минимум 3 спорта, максимум 15.
        Применяет изменения к config.SPORTS.

        Returns:
            dict с ключами: added, removed, reasoning.
        """
        default: dict[str, Any] = {
            "added": [],
            "removed": [],
            "reasoning": "Оптимизация спортов недоступна",
        }

        if ai_router is None:
            logger.debug("ai_router недоступен, спорты не изменены")
            return default

        # Собираем статистику арбитражей по спорту
        stats = memory.get_stats()
        daily_pnl = memory.get_daily_pnl(14)

        current_sports = list(config.SPORTS)

        prompt = (
            "Ты - эксперт по выбору спортивных лиг для арбитража.\n"
            "Проанализируй, какие лиги приносят больше всего арбов, а какие пусты.\n\n"
            f"Текущие спорты ({len(current_sports)}): {', '.join(current_sports)}\n"
            f"Статистика: арбитражей={stats.get('total_arbs', 0)}, "
            f"PnL={stats.get('total_pnl', 0.0):.2f}\n\n"
            "Рекомендуй какие спорты добавить и какие убрать.\n"
            "Ограничения: минимум 3 спорта, максимум 15.\n"
            "Доступные ключи: soccer_epl, soccer_spain_la_liga, soccer_italy_serie_a, "
            "soccer_germany_bundesliga, soccer_france_ligue_one, basketball_nba, "
            "basketball_euroleague, tennis_atp_french_open, americanfootball_nfl, "
            "icehockey_nhl, baseball_mlb, mma_mixed_martial_arts, cricket_ipl, "
            "rugby_league_nrl, boxing_boxing.\n\n"
            "Ответь строго JSON:\n"
            '{"add": ["sport_key1"], "remove": ["sport_key2"], '
            '"reasoning": "<обоснование>"}'
        )

        try:
            resp = await ai_router.call_llm_json(
                session,
                prompt,
                max_output_tokens=256,
                temperature=0.3,
                timeout=25,
            )
        except Exception as exc:
            logger.warning("Ошибка LLM в smart_sport_selection: %s", exc)
            return default

        if resp is None:
            return default

        to_add = resp.get("add", [])
        to_remove = resp.get("remove", [])
        reasoning = str(resp.get("reasoning", "нет обоснования"))

        # Применяем изменения с ограничениями
        new_sports = list(current_sports)
        actually_added: list[str] = []
        actually_removed: list[str] = []

        for sport in to_add:
            if isinstance(sport, str) and sport not in new_sports and len(new_sports) < 15:
                new_sports.append(sport)
                actually_added.append(sport)

        for sport in to_remove:
            if isinstance(sport, str) and sport in new_sports and len(new_sports) > 3:
                new_sports.remove(sport)
                actually_removed.append(sport)

        # Применяем к конфигу
        if actually_added or actually_removed:
            config.SPORTS = new_sports
            logger.info(
                "smart_sport_selection: добавлено=%s, убрано=%s",
                actually_added, actually_removed,
            )
            # Сохраняем в AI learnings
            memory.save_ai_learning(
                rule_type="sport_selection",
                rule_text=(
                    f"Added: {actually_added}, Removed: {actually_removed}. {reasoning}"
                ),
                confidence=0.7,
                source="ai_optimizer",
            )

        return {
            "added": actually_added,
            "removed": actually_removed,
            "reasoning": reasoning,
        }


async def optimizer_loop(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
    """Фоновый цикл оптимизации (раз в 7 дней).

    Проверяет last_run_ts в state и запускает оптимизацию если прошло достаточно времени.
    """
    optimizer = ThresholdOptimizer()
    check_interval = 3600  # проверяем каждый час

    while True:
        try:
            last_run = state.get("optimizer_last_run_ts", 0.0)
            now = time.time()

            if now - last_run >= _OPTIMIZE_INTERVAL_SEC:
                # Save old values for the notification
                old_profit = config.MIN_ARB_PROFIT
                old_edge = config.MIN_VALUE_EDGE
                old_interval = config.SCAN_INTERVAL_SEC

                result = await optimizer.optimize(session)
                state["optimizer_last_run_ts"] = now
                state["optimizer_last_result"] = result

                # Smart sport selection (alongside threshold optimization)
                sport_result = await optimizer.smart_sport_selection(session)
                state["sport_selection_result"] = sport_result

                # Notify operator via Telegram about threshold changes
                new_profit = result.get("min_arb_profit", old_profit)
                new_edge = result.get("min_value_edge", old_edge)
                new_interval = result.get("scan_interval", old_interval)
                reasoning = result.get("reasoning", "")

                if (new_profit != old_profit or new_edge != old_edge or new_interval != old_interval):
                    card = (
                        "<b>AI Optimizer: пороги обновлены</b>\n\n"
                        f"<code>min_arb_profit: {old_profit:.2f}% -> {new_profit:.2f}%</code>\n"
                        f"<code>min_value_edge: {old_edge:.2f}% -> {new_edge:.2f}%</code>\n"
                        f"<code>scan_interval:  {old_interval}s -> {new_interval}s</code>\n\n"
                        f"<i>{reasoning}</i>"
                    )
                    try:
                        await telegram_bot.send_message(session, card)
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Ошибка отправки уведомления optimizer: %s", exc)

                logger.info("optimizer_loop: оптимизация выполнена")
        except Exception as exc:
            logger.error("optimizer_loop ошибка: %s", exc)

        await asyncio.sleep(check_interval)
