"""AI-фильтр арбитражных возможностей.

Использует LLM (через корневой ai_router) для оценки вероятности того,
что найденный арбитраж реальный, а не ловушка букмекера.
Обогащает промпт выученными правилами, статистикой букмекеров,
скоростью движения линий и временем до события.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
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


# TTL кэша результатов (секунды)
_CACHE_TTL: int = 300  # 5 минут


class ArbFilter:
    """Оценивает арбитражные возможности через LLM."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        # Кэш коэффициентов для вычисления line_velocity (instance-level, с TTL)
        self._odds_cache: dict[str, tuple[float, list[float]]] = {}
        self._CACHE_TTL: float = 600.0  # 10 минут TTL для записей кэша коэффициентов

    def _cache_key(self, opportunity: dict[str, Any]) -> str:
        """Генерация ключа кэша из основных параметров возможности."""
        parts = [
            str(opportunity.get("sport", "")),
            str(opportunity.get("event", "")),
            str(opportunity.get("bookmakers", "")),
            str(opportunity.get("profit_pct", "")),
        ]
        return "|".join(parts)

    def _get_cached(self, key: str) -> Optional[dict[str, Any]]:
        """Получить результат из кэша, если TTL не истёк."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, result = entry
        if time.time() - ts > _CACHE_TTL:
            del self._cache[key]
            return None
        return result

    def _set_cached(self, key: str, result: dict[str, Any]) -> None:
        """Сохранить результат в кэш."""
        self._cache[key] = (time.time(), result)

    def _compute_line_velocity(self, opportunity: dict[str, Any]) -> Optional[float]:
        """Вычислить скорость изменения линии из кэша коэффициентов."""
        event_key = str(opportunity.get("event", ""))
        odds = opportunity.get("odds", [])
        if not event_key or not odds:
            return None

        now = time.time()

        # Прореживаем записи старше TTL перед использованием кэша
        expired_keys = [
            k for k, (ts, _) in self._odds_cache.items()
            if now - ts > self._CACHE_TTL
        ]
        for k in expired_keys:
            del self._odds_cache[k]

        cached = self._odds_cache.get(event_key)

        if cached is not None:
            prev_ts, prev_odds = cached
            elapsed = now - prev_ts
            if elapsed > 0 and prev_odds:
                # Средняя скорость по всем коэффициентам
                deltas = []
                for i in range(min(len(odds), len(prev_odds))):
                    deltas.append((odds[i] - prev_odds[i]) / elapsed)
                if deltas:
                    velocity = sum(abs(d) for d in deltas) / len(deltas)
                    # Обновляем кэш
                    self._odds_cache[event_key] = (now, list(odds))
                    return velocity

        # Первый снимок - сохраняем
        self._odds_cache[event_key] = (now, list(odds))
        return None

    def _compute_time_to_event(self, opportunity: dict[str, Any]) -> Optional[float]:
        """Вычислить время до события в минутах из commence_time."""
        details = opportunity.get("details", {})
        commence_time = details.get("commence_time", "")
        if not commence_time:
            return None

        try:
            # Парсим ISO формат
            if commence_time.endswith("Z"):
                commence_time = commence_time[:-1] + "+00:00"
            ct = datetime.fromisoformat(commence_time)
            if ct.tzinfo is None:
                ct = ct.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = (ct - now).total_seconds() / 60.0
            return max(0.0, delta)
        except (ValueError, TypeError):
            return None

    async def evaluate(self, opportunity: dict[str, Any]) -> dict[str, Any]:
        """Оценить арбитражную возможность через LLM.

        Возвращает dict с ключами:
          - score: int 0-100 (вероятность что арб живой)
          - reasoning: str (обоснование)
          - is_live: bool (score > 50)
        """
        cache_key = self._cache_key(opportunity)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # Обогащаем контекст
        line_velocity = self._compute_line_velocity(opportunity)
        time_to_event_min = self._compute_time_to_event(opportunity)

        # Получаем выученные правила и статистику букмекеров
        ai_learnings = memory.get_ai_learnings(limit=10)
        bookmakers = opportunity.get("bookmakers", [])
        bm_stats: dict[str, dict[str, Any]] = {}
        for bm in bookmakers:
            if bm:
                bm_stats[bm] = memory.get_bookmaker_stats(bm)

        prompt = self._build_prompt(
            opportunity,
            line_velocity=line_velocity,
            time_to_event_min=time_to_event_min,
            ai_learnings=ai_learnings,
            bm_stats=bm_stats,
        )

        if ai_router is None:
            result = {
                "score": 50,
                "reasoning": "ai_router недоступен (не установлен)",
                "is_live": False,
            }
            self._set_cached(cache_key, result)
            return result

        try:
            resp = await ai_router.call_llm_json(
                self._session,
                prompt,
                max_output_tokens=256,
                temperature=0.2,
                timeout=20,
            )
        except Exception as exc:
            print(f"[AI_FILTER] Ошибка вызова LLM: {exc}")
            resp = None

        if resp is None:
            # AI недоступен - возвращаем нейтральную оценку
            result: dict[str, Any] = {
                "score": 50,
                "reasoning": "AI-оценка недоступна",
                "is_live": False,
            }
            return result

        score = int(resp.get("score", 50))
        score = max(0, min(100, score))
        reasoning = str(resp.get("reasoning", "нет обоснования"))

        result = {
            "score": score,
            "reasoning": reasoning,
            "is_live": score > 50,
        }

        self._set_cached(cache_key, result)
        return result

    def _build_prompt(
        self,
        opportunity: dict[str, Any],
        line_velocity: Optional[float] = None,
        time_to_event_min: Optional[float] = None,
        ai_learnings: Optional[list[dict[str, Any]]] = None,
        bm_stats: Optional[dict[str, dict[str, Any]]] = None,
    ) -> str:
        """Сформировать промпт для LLM-оценки арбитража."""
        sport = opportunity.get("sport", "неизвестно")
        event = opportunity.get("event", "неизвестно")
        bookmakers = opportunity.get("bookmakers", [])
        profit_pct = opportunity.get("profit_pct", 0.0)
        odds = opportunity.get("odds", {})

        # Время до события
        if time_to_event_min is not None:
            time_str = f"{time_to_event_min:.0f}"
        else:
            time_str = "неизвестно"

        # Движение линии
        if line_velocity is not None:
            line_movement = f"{line_velocity:.6f} ед/сек"
        else:
            details = opportunity.get("details", {})
            lv = details.get("line_velocity")
            if lv is not None:
                line_movement = f"{lv:.6f} ед/сек"
            else:
                line_movement = "нет данных"

        prompt = (
            "Ты - эксперт по спортивным ставкам и арбитражу. "
            "Оцени вероятность того, что данная арбитражная возможность реальна "
            "(а не ловушка букмекера или устаревшая линия).\n\n"
            f"Спорт: {sport}\n"
            f"Событие: {event}\n"
            f"Букмекеры: {bookmakers}\n"
            f"Коэффициенты: {odds}\n"
            f"Прибыль: {profit_pct:.2f}%\n"
            f"Время до события: {time_str} мин\n"
            f"Движение линии: {line_movement}\n"
        )

        # Статистика букмекеров
        if bm_stats:
            prompt += "\nСтатистика букмекеров:\n"
            for bm_name, stats in bm_stats.items():
                prompt += (
                    f"  {bm_name}: ставок={stats.get('total_bets', 0)}, "
                    f"отмен={stats.get('cancelled_pct', 0):.1f}%, "
                    f"avg_pnl={stats.get('avg_pnl', 0):.4f}, "
                    f"trap_rate={stats.get('trap_rate', 0):.1f}%\n"
                )

        # Выученные правила
        if ai_learnings:
            prompt += "\nВыученные правила (из анализа истории):\n"
            for rule in ai_learnings:
                prompt += (
                    f"  [{rule.get('rule_type', '')}] "
                    f"{rule.get('rule_text', '')} "
                    f"(уверенность: {rule.get('confidence', 0):.2f})\n"
                )

        prompt += (
            "\nУчитывай:\n"
            "1. Скорость движения линии (быстрое движение = высокий риск)\n"
            "2. Репутация букмекера (soft vs sharp bookmaker)\n"
            "3. Тип спорта (теннис/live = выше риск устаревших коэфф.)\n"
            "4. Размер расхождения (слишком большой = вероятно ловушка)\n"
            "5. Время до события (чем ближе, тем быстрее меняются линии)\n"
            "6. Статистика букмекера (высокий trap_rate = опасно)\n"
            "7. Выученные правила из истории\n\n"
            "Ответь строго в формате JSON:\n"
            '{"score": <0-100>, "reasoning": "<краткое обоснование на русском>"}\n'
            "score = вероятность что арбитраж реален и доступен для исполнения."
        )
        return prompt
