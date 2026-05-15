"""Модуль расчёта ставок и самообучения AI-фильтра.

SettlementEngine:
  - settle_bets: расчёт PENDING/SIMULATED ставок (WON/LOST на основе реальных результатов)
  - learn: анализ 7 дней данных, генерация правил через LLM, сохранение в БД
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import aiohttp

from arbitrage import config, memory
from arbitrage.odds_api import OddsAPIClient

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

    def __init__(self, session: aiohttp.ClientSession | None = None) -> None:
        self._session: aiohttp.ClientSession | None = session

    async def settle_bets(self, session: aiohttp.ClientSession) -> None:
        """Расчёт PENDING/SIMULATED ставок на основе реальных результатов.

        Для каждой ставки запрашивает реальные результаты через OddsAPI.
        Для h2h: сравниваем счёт и определяем победителя.
        Для totals: сумма голов vs линия.
        Если матч не завершён - оставляем PENDING.
        Если нет данных - ставим UNRESOLVED.
        Для DRY_RUN/SIMULATED ставок: SIMULATED_WON / SIMULATED_LOST.
        """
        pending = memory.get_pending_bets_for_settlement()
        if not pending:
            return

        print(f"[SETTLEMENT] Расчёт {len(pending)} ставок")

        odds_client = OddsAPIClient(session=session)

        # Кэш результатов по спортам (чтобы не делать повторные запросы)
        scores_cache: dict[str, list[dict[str, Any]]] = {}

        # Агрегация PnL по дням
        daily_agg: dict[str, dict[str, float]] = defaultdict(
            lambda: {"staked": 0.0, "won": 0.0, "pnl": 0.0}
        )

        for bet in pending:
            bet_id: int = bet["id"]
            odds: float = bet.get("odds", 0.0)
            stake: float = bet.get("stake", 0.0)
            ts_str: str = bet.get("ts", "")
            outcome_name: str = bet.get("outcome", "")

            # Определяем дату ставки
            try:
                bet_date = ts_str[:10]  # YYYY-MM-DD
            except (IndexError, TypeError):
                bet_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            if odds <= 1.0:
                # Невалидные коэффициенты - VOID
                memory.update_bet_result(bet_id, "VOID", 0.0)
                continue

            # Определяем спорт из arb record
            arb_id: int = bet.get("arb_id", 0)
            sport = self._get_sport_for_bet(bet)

            if not sport:
                memory.update_bet_result(bet_id, "UNRESOLVED", 0.0)
                continue

            # Получаем результаты (с кэшированием)
            if sport not in scores_cache:
                try:
                    scores_cache[sport] = await odds_client.get_scores(sport)
                except Exception as exc:
                    print(f"[SETTLEMENT] Ошибка получения scores для {sport}: {exc}")
                    scores_cache[sport] = []

            scores = scores_cache[sport]

            if not scores:
                memory.update_bet_result(bet_id, "UNRESOLVED", 0.0)
                continue

            # Ищем событие по названиям команд
            event_name: str = bet.get("event", "")
            match_data = self._find_match(scores, event_name)

            if match_data is None:
                memory.update_bet_result(bet_id, "UNRESOLVED", 0.0)
                continue

            # Проверяем, завершён ли матч
            if not match_data.get("completed", False):
                # Матч ещё не завершён - оставляем PENDING
                continue

            # Определяем результат
            result = self._determine_result(match_data, outcome_name, bet)

            if result is None:
                memory.update_bet_result(bet_id, "UNRESOLVED", 0.0)
                continue

            # Для DRY_RUN ставок используем SIMULATED_ префикс
            is_simulated = config.DRY_RUN or bet.get("result", "") == "SIMULATED"

            if result == "WON":
                pnl = stake * (odds - 1.0)
                final_result = "SIMULATED_WON" if is_simulated else "WON"
            else:
                pnl = -stake
                final_result = "SIMULATED_LOST" if is_simulated else "LOST"

            memory.update_bet_result(bet_id, final_result, pnl)

            # Агрегация
            daily_agg[bet_date]["staked"] += stake
            if "WON" in final_result:
                daily_agg[bet_date]["won"] += stake * odds
            daily_agg[bet_date]["pnl"] += pnl

        # Обновляем daily_pnl
        for date_str, agg in daily_agg.items():
            staked = agg["staked"]
            roi = (agg["pnl"] / staked * 100.0) if staked > 0 else 0.0
            memory.update_daily_pnl(date_str, staked, agg["won"], agg["pnl"], roi)

        print(f"[SETTLEMENT] Расчёт завершён. Дней обновлено: {len(daily_agg)}")

    @staticmethod
    def _get_sport_for_bet(bet: dict[str, Any]) -> str:
        """Извлекает ключ спорта из записи ставки/арба."""
        # Спорт может быть доступен напрямую из JOIN
        sport = bet.get("sport", "")
        if sport:
            return sport
        # Fallback: получаем спорт из arb record через memory
        arb_id: int = bet.get("arb_id", 0)
        if arb_id:
            arb = memory.get_arb_by_id(arb_id)
            if arb:
                return arb.get("sport", "")
        return ""

    @staticmethod
    def _find_match(
        scores: list[dict[str, Any]], event_name: str
    ) -> dict[str, Any] | None:
        """Ищет матч в списке результатов по названию события/команд."""
        if not event_name:
            return None

        # Разделяем event_name на команды (формат: "Team A vs Team B" или "Team A - Team B")
        parts = re.split(r"\s+vs\.?\s+|\s+-\s+", event_name, maxsplit=1)
        if len(parts) == 2:
            home_search = parts[0].strip().lower()
            away_search = parts[1].strip().lower()
        else:
            home_search = event_name.lower()
            away_search = ""

        for score_event in scores:
            home_team = score_event.get("home_team", "").lower()
            away_team = score_event.get("away_team", "").lower()

            # Точное совпадение
            if home_team == home_search and away_team == away_search:
                return score_event

            # Частичное совпадение (подстрока)
            if (
                home_search
                and away_search
                and home_search in home_team
                and away_search in away_team
            ):
                return score_event

            # Совпадение по полному имени события
            event_display = f"{home_team} vs {away_team}"
            if event_name.lower() in event_display or event_display in event_name.lower():
                return score_event

        return None

    @staticmethod
    def _determine_result(
        match_data: dict[str, Any], outcome_name: str, bet: dict[str, Any]
    ) -> str | None:
        """Определяет результат ставки на основе счёта матча.

        Returns:
            'WON', 'LOST', или None если невозможно определить.
        """
        scores_list = match_data.get("scores", [])
        if not scores_list:
            return None

        # Парсим счёт: [{"name": "Team A", "score": "2"}, {"name": "Team B", "score": "1"}]
        home_team = match_data.get("home_team", "")
        away_team = match_data.get("away_team", "")

        home_score: int | None = None
        away_score: int | None = None

        for score_entry in scores_list:
            team_name = score_entry.get("name", "")
            score_val = score_entry.get("score", "")
            try:
                score_int = int(score_val)
            except (ValueError, TypeError):
                continue

            if team_name == home_team:
                home_score = score_int
            elif team_name == away_team:
                away_score = score_int

        if home_score is None or away_score is None:
            return None

        # Определяем тип ставки из outcome_name
        outcome_lower = outcome_name.lower().strip()

        # Проверяем totals (Over/Under X.X)
        over_match = re.match(r"over\s+([\d.]+)", outcome_lower)
        under_match = re.match(r"under\s+([\d.]+)", outcome_lower)

        if over_match:
            line = float(over_match.group(1))
            total = home_score + away_score
            return "WON" if total > line else "LOST"

        if under_match:
            line = float(under_match.group(1))
            total = home_score + away_score
            return "WON" if total < line else "LOST"

        # H2H: определяем победителя
        if home_score > away_score:
            winner = home_team
        elif away_score > home_score:
            winner = away_team
        else:
            winner = "Draw"

        # Сравниваем с outcome_name
        if outcome_lower == "draw" or outcome_lower == "ничья":
            return "WON" if winner == "Draw" else "LOST"

        if outcome_name == home_team or outcome_name == away_team:
            return "WON" if outcome_name == winner else "LOST"

        # Частичное совпадение
        if home_team.lower() in outcome_lower or outcome_lower in home_team.lower():
            return "WON" if winner == home_team else "LOST"
        if away_team.lower() in outcome_lower or outcome_lower in away_team.lower():
            return "WON" if winner == away_team else "LOST"

        return None

    async def learn(self, session: aiohttp.ClientSession) -> None:
        """Самообучение: анализ 7 дней данных и генерация правил через LLM.

        Анализирует:
          - букмекеры с высоким % отмен/проигрышей
          - наиболее прибыльные типы арбитража
          - рабочие пороги profit_pct
        Вызывает LLM для генерации правил, сохраняет в ai_learnings.

        Примечание: в DRY_RUN все ставки симулированы. Обучение на таких данных
        допускается только для проверки пайплайна. Правила из симуляции
        не должны смешиваться с реальными данными.
        """
        if ai_router is None:
            print("[SETTLEMENT] ai_router недоступен, обучение пропущено")
            return

        # Получаем данные за 7 дней
        daily_data = memory.get_daily_pnl(days=7)
        recent_bets = memory.get_recent_bets(limit=200)

        # Проверяем наличие реальных (не симулированных) ставок
        has_real_bets = any(
            bet.get("status") not in ("SIMULATED", None)
            and bet.get("result") in ("WON", "LOST")
            for bet in (recent_bets or [])
        )
        if not has_real_bets:
            # Все ставки симулированные - логируем явно, что обучение на тестовых данных
            print("[SETTLEMENT] Обучение на симулированных данных (тестовый режим)")

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
