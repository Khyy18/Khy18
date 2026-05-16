"""CLV (Closing Line Value) трекер.

Отслеживает, обыгрывает ли бот закрывающие линии букмекеров.
Положительный CLV означает, что ставка была размещена по более
выгодным коэффициентам, чем финальные (закрывающие) линии.

CLV% = (placement_odds / closing_odds - 1) * 100
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import aiohttp

from arbitrage import memory
from arbitrage.odds_api import OddsAPIClient

logger = logging.getLogger(__name__)


class CLVTracker:
    """Трекер Closing Line Value для оценки качества ставок."""

    def record_bet_placement(
        self,
        bet_id: int,
        event_id: str,
        odds: float,
        sport: str,
        outcome: str = "",
    ) -> Optional[int]:
        """Записывает ставку в момент размещения для последующего CLV-анализа.

        Args:
            bet_id: ID ставки в таблице bets.
            event_id: уникальный идентификатор события.
            odds: коэффициент в момент размещения.
            sport: ключ вида спорта (например 'soccer_epl').
            outcome: название исхода (например 'Home', 'Away', 'Draw').

        Returns:
            ID записи в clv_records или None при ошибке.
        """
        record_id = memory.save_clv_record(
            bet_id=bet_id,
            event_id=event_id,
            sport=sport,
            placement_odds=odds,
            outcome=outcome,
        )
        if record_id:
            logger.info(
                "[CLV] Записана ставка #%d, event=%s, odds=%.3f, outcome=%s",
                bet_id,
                event_id,
                odds,
                outcome,
            )
        return record_id

    async def check_closing_lines(
        self, session: aiohttp.ClientSession
    ) -> None:
        """Проверяет закрывающие линии для записей старше 30 минут.

        Получает текущие коэффициенты через OddsAPI и рассчитывает CLV%
        для каждой ожидающей проверки записи.
        """
        pending = memory.get_pending_clv_checks()
        if not pending:
            logger.debug("[CLV] Нет записей для проверки закрывающих линий")
            return

        logger.info("[CLV] Проверка закрывающих линий: %d записей", len(pending))

        # Группируем по спорту для минимизации API-запросов
        sports_map: dict[str, list[dict[str, Any]]] = {}
        for record in pending:
            sport = record["sport"]
            if sport not in sports_map:
                sports_map[sport] = []
            sports_map[sport].append(record)

        client = OddsAPIClient(session=session)

        for sport, records in sports_map.items():
            try:
                events = await client.get_odds(sport)
            except Exception as e:
                logger.error(
                    "[CLV] Ошибка получения коэффициентов для %s: %s",
                    sport,
                    e,
                )
                continue

            # Индексируем события по event_id
            events_by_id: dict[str, dict[str, Any]] = {}
            for ev in events:
                eid = ev.get("event_id") or ev.get("id", "")
                if eid:
                    events_by_id[eid] = ev

            for record in records:
                event_id = record["event_id"]
                event_data = events_by_id.get(event_id)

                if not event_data:
                    logger.debug(
                        "[CLV] Событие %s не найдено в текущих данных",
                        event_id,
                    )
                    continue

                # Берём закрывающую линию Pinnacle для конкретного исхода
                record_outcome = record.get("outcome", "") or None
                closing_odds = self._extract_best_odds(event_data, outcome=record_outcome)
                if closing_odds is None or closing_odds <= 1.0:
                    continue

                placement_odds = record["placement_odds"]
                clv_pct = (placement_odds / closing_odds - 1.0) * 100.0

                memory.update_clv_record(
                    record_id=record["id"],
                    closing_odds=closing_odds,
                    clv_pct=clv_pct,
                )
                logger.info(
                    "[CLV] Запись #%d: placement=%.3f, closing=%.3f, CLV=%.2f%%",
                    record["id"],
                    placement_odds,
                    closing_odds,
                    clv_pct,
                )

    def get_clv_stats(self) -> dict[str, Any]:
        """Возвращает статистику CLV.

        Returns:
            {"avg_clv_pct": float, "positive_count": int,
             "negative_count": int, "total_checked": int}
        """
        return memory.get_clv_stats()

    @staticmethod
    def _extract_best_odds(
        event_data: dict[str, Any], outcome: Optional[str] = None
    ) -> Optional[float]:
        """Извлекает закрывающий коэффициент из данных события (Pinnacle).

        Использует Pinnacle как эталон закрывающей линии.
        Если outcome указан, фильтрует по имени исхода.
        Если Pinnacle недоступен, берёт максимальный среди sharp-бк.
        """
        pinnacle_best: Optional[float] = None
        fallback_best: Optional[float] = None
        bookmakers = event_data.get("bookmakers", [])

        for bk in bookmakers:
            bk_key: str = bk.get("key", "").lower()
            is_pinnacle = bk_key == "pinnacle"
            markets = bk.get("markets", [])
            for market in markets:
                if market.get("key") != "h2h":
                    continue
                outcomes = market.get("outcomes", [])
                for oc in outcomes:
                    price = oc.get("price")
                    if price and isinstance(price, (int, float)) and price > 1.0:
                        # Если outcome указан, фильтруем по имени
                        if outcome and oc.get("name") != outcome:
                            continue
                        if is_pinnacle:
                            if pinnacle_best is None or price > pinnacle_best:
                                pinnacle_best = float(price)
                        else:
                            if fallback_best is None or price > fallback_best:
                                fallback_best = float(price)

        return pinnacle_best if pinnacle_best is not None else fallback_best
