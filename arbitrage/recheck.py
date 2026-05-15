"""Перепроверка коэффициентов перед исполнением ставки.

RecheckEngine повторно запрашивает коэффициенты из OddsAPI и верифицирует,
что арбитраж всё ещё жив. Если коэффициенты сдвинулись более чем на 0.5%,
арбитраж отменяется. Также включает AI-предсказание TTL возможности.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any, Optional

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

logger = logging.getLogger(__name__)

# Максимально допустимый дрифт коэффициентов (%)
_MAX_ODDS_DRIFT_PCT: float = 0.5


class RecheckEngine:
    """Перепроверяет арбитражные возможности перед исполнением."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session: aiohttp.ClientSession = session
        self._odds_client: OddsAPIClient = OddsAPIClient(session=session)
        # Кэш свежих данных по спорту для батчевой перепроверки
        self._sport_cache: dict[str, list[dict[str, Any]]] = {}

    async def recheck_batch(
        self, session: aiohttp.ClientSession, opportunities: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Перепроверить батч возможностей, группируя запросы по спорту.

        Вызывает get_odds один раз на каждый уникальный спорт, затем
        верифицирует каждую возможность по кэшированному ответу.

        Args:
            session: aiohttp-сессия
            opportunities: список возможностей для проверки

        Returns:
            Список подтвержденных возможностей
        """
        # Собираем уникальные спорты из всех возможностей
        sport_keys: set[str] = set()
        for opp in opportunities:
            sport = opp.get("sport", "")
            if sport:
                sport_keys.add(sport)

        # Один запрос на каждый уникальный спорт
        self._sport_cache.clear()
        for sport in sport_keys:
            try:
                fresh_events = await self._odds_client.get_odds(sport)
                self._sport_cache[sport] = fresh_events
            except Exception as exc:
                logger.error("Recheck: ошибка запроса OddsAPI для %s: %s", sport, exc)
                # При ошибке сети - кэшируем пустой список, fail-open
                self._sport_cache[sport] = []

        # Верифицируем каждую возможность по кэшированным данным
        confirmed: list[dict[str, Any]] = []
        for opp in opportunities:
            try:
                alive = await self.recheck_opportunity(session, opp)
                if alive:
                    confirmed.append(opp)
            except Exception as exc:
                logger.warning("Recheck: ошибка проверки: %s", exc)
                confirmed.append(opp)  # fail-open

        return confirmed

    async def recheck_opportunity(
        self, session: aiohttp.ClientSession, opportunity: dict[str, Any]
    ) -> bool:
        """Перепроверить арбитражную возможность.

        Использует кэшированные данные из recheck_batch если доступны,
        иначе запрашивает заново (для обратной совместимости).

        Args:
            session: aiohttp-сессия
            opportunity: словарь с данными арбитража

        Returns:
            True если арбитраж подтверждён, False если умер
        """
        sport: str = opportunity.get("sport", "")
        event_name: str = opportunity.get("event_name", opportunity.get("event", ""))
        opp_type: str = opportunity.get("type", "surebet")
        original_odds: list[float] = opportunity.get("odds", [])

        if not sport or not original_odds:
            logger.warning("Recheck: недостаточно данных для проверки %s", event_name)
            return False

        # Используем кэшированные данные если доступны (батчевый режим)
        if sport in self._sport_cache:
            fresh_events = self._sport_cache[sport]
            # Пустой кэш означает ошибку сети - fail-open
            if not fresh_events:
                return True
        else:
            # Fallback: одиночный запрос (обратная совместимость)
            try:
                fresh_events = await self._odds_client.get_odds(sport)
            except Exception as exc:
                logger.error("Recheck: ошибка запроса OddsAPI: %s", exc)
                # При ошибке сети - пропускаем (не блокируем)
                return True

        # Ищем нужное событие среди свежих данных
        target_event: Optional[dict[str, Any]] = None
        home: str = opportunity.get("home", "")
        away: str = opportunity.get("away", "")
        for ev in fresh_events:
            if ev.get("home_team") == home and ev.get("away_team") == away:
                target_event = ev
                break

        if target_event is None:
            logger.info("Recheck: событие %s не найдено - арб мёртв", event_name)
            self._log_arb_died(opportunity, "событие не найдено в свежих данных")
            return False

        # Проверяем по типу арбитража
        if opp_type == "surebet":
            alive = self._verify_surebet(target_event, opportunity)
        elif opp_type in ("surebet_totals", "surebet_spreads"):
            alive = self._verify_surebet(target_event, opportunity)
        elif opp_type == "value_bet":
            alive = self._verify_value_bet(target_event, opportunity)
        else:
            alive = True

        if not alive:
            self._log_arb_died(opportunity, "коэффициенты сдвинулись")
            return False

        # Проверяем дрифт коэффициентов
        fresh_odds = self._extract_fresh_odds(target_event, opportunity)
        if fresh_odds and not self._check_drift(original_odds, fresh_odds):
            self._log_arb_died(opportunity, f"дрифт > {_MAX_ODDS_DRIFT_PCT}%")
            return False

        # AI TTL предсказание
        ttl_seconds = await self._predict_ttl(session, opportunity)
        if ttl_seconds is not None:
            opportunity["predicted_ttl_sec"] = ttl_seconds

        return True

    def _verify_surebet(
        self, event: dict[str, Any], opportunity: dict[str, Any]
    ) -> bool:
        """Проверяет, что surebet ещё жив (sum(1/odds) < 1)."""
        opp_type: str = opportunity.get("type", "surebet")
        market_key: str = "h2h"
        if opp_type == "surebet_totals":
            market_key = "totals"
        elif opp_type == "surebet_spreads":
            market_key = "spreads"

        outcomes_map: dict[str, list[tuple[float, str]]] = {}
        for bm in event.get("bookmakers", []):
            bm_key: str = bm.get("key", "")
            for market in bm.get("markets", []):
                if market.get("key") != market_key:
                    continue
                for outcome in market.get("outcomes", []):
                    name: str = outcome.get("name", "")
                    price: float = outcome.get("price", 0.0)
                    if name and price > 1.0:
                        if name not in outcomes_map:
                            outcomes_map[name] = []
                        outcomes_map[name].append((price, bm_key))

        if len(outcomes_map) < 2:
            return False

        best_odds: list[float] = []
        for outcome_offers in outcomes_map.values():
            if not outcome_offers:
                return False
            best = max(outcome_offers, key=lambda x: x[0])
            best_odds.append(best[0])

        inverse_sum: float = sum(1.0 / o for o in best_odds if o > 0)
        return inverse_sum < 1.0

    def _verify_value_bet(
        self, event: dict[str, Any], opportunity: dict[str, Any]
    ) -> bool:
        """Проверяет, что value bet ещё жив (edge > MIN_VALUE_EDGE)."""
        details: dict[str, Any] = opportunity.get("details", {})
        sharp_prob: float = details.get("sharp_prob", 0.0)
        if sharp_prob <= 0:
            return True  # Нет данных для проверки

        bookmakers_list: list[str] = opportunity.get("bookmakers", [])
        target_bm: str = bookmakers_list[0] if bookmakers_list else ""

        for bm in event.get("bookmakers", []):
            if bm.get("key", "") != target_bm:
                continue
            for market in bm.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                for outcome in market.get("outcomes", []):
                    price: float = outcome.get("price", 0.0)
                    if price <= 1.0:
                        continue
                    implied_value: float = price * sharp_prob
                    edge: float = (implied_value - 1.0) * 100.0
                    if edge >= config.MIN_VALUE_EDGE:
                        return True

        return False

    def _extract_fresh_odds(
        self, event: dict[str, Any], opportunity: dict[str, Any]
    ) -> list[float]:
        """Извлекает свежие лучшие коэффициенты для сравнения с оригиналом."""
        opp_type: str = opportunity.get("type", "surebet")
        market_key: str = "h2h"
        if opp_type == "surebet_totals":
            market_key = "totals"
        elif opp_type == "surebet_spreads":
            market_key = "spreads"

        outcomes_map: dict[str, list[float]] = {}
        for bm in event.get("bookmakers", []):
            for market in bm.get("markets", []):
                if market.get("key") != market_key:
                    continue
                for outcome in market.get("outcomes", []):
                    name: str = outcome.get("name", "")
                    price: float = outcome.get("price", 0.0)
                    if name and price > 1.0:
                        if name not in outcomes_map:
                            outcomes_map[name] = []
                        outcomes_map[name].append(price)

        best_odds: list[float] = []
        for offers in outcomes_map.values():
            if offers:
                best_odds.append(max(offers))
        return best_odds

    @staticmethod
    def _check_drift(original: list[float], fresh: list[float]) -> bool:
        """Проверяет что дрифт коэффициентов не превышает порог.

        Returns:
            True если дрифт в пределах нормы, False если превышен
        """
        if len(original) != len(fresh):
            return True  # Нельзя сравнить - пропускаем

        for orig, curr in zip(original, fresh):
            if orig <= 0:
                continue
            drift_pct: float = abs(curr - orig) / orig * 100.0
            if drift_pct > _MAX_ODDS_DRIFT_PCT:
                return False
        return True

    @staticmethod
    def _log_arb_died(opportunity: dict[str, Any], reason: str) -> None:
        """Логирует в память что арб умер до исполнения."""
        event_name: str = opportunity.get("event_name", opportunity.get("event", ""))
        logger.info("Арб умер до исполнения: %s | причина: %s", event_name, reason)
        memory.record_arb(
            sport=opportunity.get("sport", ""),
            event=event_name,
            arb_type=opportunity.get("type", "surebet"),
            bookmakers=opportunity.get("bookmakers", []),
            odds={"odds": opportunity.get("odds", [])},
            profit_pct=opportunity.get("profit_pct", 0.0),
            edge_pct=opportunity.get("edge_pct", 0.0),
            ai_score=opportunity.get("ai_score", 0),
            status="DIED_BEFORE_EXEC",
        )

    async def _predict_ttl(
        self, session: aiohttp.ClientSession, opportunity: dict[str, Any]
    ) -> Optional[int]:
        """AI-предсказание TTL (время жизни) арбитража в секундах.

        Args:
            session: aiohttp-сессия
            opportunity: данные арбитража

        Returns:
            Предсказанное количество секунд или None если AI недоступен
        """
        if ai_router is None:
            return None

        sport: str = opportunity.get("sport", "")
        profit_pct: float = opportunity.get("profit_pct", 0.0)
        bookmakers: list[str] = opportunity.get("bookmakers", [])
        opp_type: str = opportunity.get("type", "surebet")

        prompt: str = (
            "Ты - эксперт по арбитражным ставкам. "
            "Оцени примерное время жизни (TTL) данной арбитражной возможности "
            "в секундах.\n\n"
            f"Спорт: {sport}\n"
            f"Тип: {opp_type}\n"
            f"Прибыль: {profit_pct:.2f}%\n"
            f"Букмекеры: {bookmakers}\n\n"
            "Учитывай:\n"
            "1. Высокопрофитные арбитражи закрываются быстрее\n"
            "2. Sharp-букмекеры реагируют быстрее soft\n"
            "3. Популярные спорты (футбол, баскетбол) имеют более короткий TTL\n"
            "4. Тотала и спреды обычно живут дольше чем h2h\n\n"
            "Ответь строго в формате JSON:\n"
            '{"ttl_seconds": <число>, "confidence": <0-100>}\n'
        )

        try:
            resp = await ai_router.call_llm_json(
                session,
                prompt,
                max_output_tokens=128,
                temperature=0.3,
                timeout=15,
            )
        except Exception as exc:
            logger.warning("Recheck TTL: ошибка AI: %s", exc)
            return None

        if resp is None:
            return None

        ttl: int = int(resp.get("ttl_seconds", 120))
        return max(10, min(3600, ttl))
