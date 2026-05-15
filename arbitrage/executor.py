"""Исполнитель ставок (executor).

В режиме DRY_RUN логирует намерения, не размещая реальные ставки.
Структура подготовлена для реального исполнения через API букмекеров.
Поддерживает параллельное исполнение ног surebet через asyncio.gather.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from arbitrage import config

logger = logging.getLogger(__name__)


# Статусы ставок
STATUS_PENDING = "PENDING"
STATUS_PLACED = "PLACED"
STATUS_CONFIRMED = "CONFIRMED"
STATUS_FAILED = "FAILED"
STATUS_SIMULATED = "SIMULATED"
STATUS_PARTIAL_FILL = "PARTIAL_FILL"


@dataclass
class ArbLeg:
    """Одна нога арбитражной ставки."""
    bookmaker: str
    outcome: str
    odds: float
    stake: float


class BetExecutor:
    """Исполнитель ставок с поддержкой dry-run режима."""

    def __init__(self) -> None:
        self.dry_run: bool = config.DRY_RUN
        self._active_bets: list[dict[str, Any]] = []

    async def execute(self, allocations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Исполнить список аллокаций (ставок).

        В dry-run режиме логирует и возвращает статус SIMULATED.
        В реальном режиме (placeholder) пытается разместить ставки.

        Если аллокация содержит ключ "legs" (surebet), все ноги
        исполняются параллельно через asyncio.gather.

        Возвращает список результатов с полями:
          bookmaker, event, outcome, stake, odds, status, ts
        """
        results: list[dict[str, Any]] = []

        for alloc in allocations:
            opp = alloc.get("opportunity", {})
            legs = alloc.get("legs")

            if legs:
                # Surebet: параллельное исполнение всех ног
                bet_result = await self._execute_surebet(legs, opp)
            else:
                # Value bet: одиночное исполнение
                bet_result = await self._execute_single(alloc)

            results.append(bet_result)
            self._active_bets.append(bet_result)

        return results

    async def _execute_surebet(
        self, legs: list[dict[str, Any]], opp: dict[str, Any]
    ) -> dict[str, Any]:
        """Исполнить surebet: все ноги параллельно."""
        event = opp.get("event", "неизвестно")
        ts = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")

        leg_results = await asyncio.gather(
            *[self._execute_single_leg(leg) for leg in legs],
            return_exceptions=True,
        )

        # Анализ результатов
        failed_legs: list[int] = []
        successful_legs: list[dict[str, Any]] = []
        for i, res in enumerate(leg_results):
            if isinstance(res, Exception):
                failed_legs.append(i)
                logger.error("[EXECUTOR] Нога %d провалилась: %s", i, res)
            elif isinstance(res, dict) and res.get("status") in (STATUS_FAILED, "NOT_IMPLEMENTED"):
                failed_legs.append(i)
            else:
                if isinstance(res, dict):
                    successful_legs.append(res)

        if failed_legs:
            status = STATUS_PARTIAL_FILL
            print(
                f"[EXECUTOR] PARTIAL_FILL: ноги {failed_legs} провалились "
                f"из {len(legs)} для {event}"
            )
        else:
            status = STATUS_SIMULATED if self.dry_run else STATUS_PLACED

        # Берем данные первой ноги как основу результата
        first_leg = legs[0] if legs else {}
        bet_result: dict[str, Any] = {
            "bookmaker": first_leg.get("bookmaker", "неизвестно"),
            "event": event,
            "outcome": first_leg.get("outcome", "неизвестно"),
            "stake": sum(leg.get("stake", 0.0) for leg in legs),
            "odds": first_leg.get("odds", 0.0),
            "status": status,
            "ts": ts,
            "legs": [r for r in leg_results if isinstance(r, dict)],
            "failed_legs": failed_legs,
        }
        return bet_result

    async def _execute_single_leg(self, leg: dict[str, Any]) -> dict[str, Any]:
        """Исполнить одну ногу арбитражной ставки."""
        bookmaker = leg.get("bookmaker", "неизвестно")
        outcome = leg.get("outcome", "неизвестно")
        odds = leg.get("odds", 0.0)
        stake = leg.get("stake", 0.0)
        ts = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")

        if self.dry_run:
            print(
                f"[EXECUTOR] DRY RUN leg: ставка {stake:.2f} @ {odds:.2f} "
                f"на {outcome} ({bookmaker})"
            )
            return {
                "bookmaker": bookmaker,
                "event": "",
                "outcome": outcome,
                "stake": stake,
                "odds": odds,
                "status": STATUS_SIMULATED,
                "ts": ts,
            }
        else:
            return await self._place_bet(bookmaker, "", outcome, stake, odds)

    async def _execute_single(self, alloc: dict[str, Any]) -> dict[str, Any]:
        """Исполнить одиночную ставку (value bet)."""
        opp = alloc.get("opportunity", {})
        stake = alloc.get("stake_amount", 0.0)
        odds = opp.get("best_odds", opp.get("odds", 0.0))
        event = opp.get("event", "неизвестно")
        outcome = opp.get("outcome", opp.get("selection", "неизвестно"))
        bookmaker = opp.get("bookmaker", opp.get("best_bookmaker", "неизвестно"))

        ts = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")

        if self.dry_run:
            print(
                f"[EXECUTOR] DRY RUN: ставка {stake} @ {odds} "
                f"на {outcome} ({bookmaker})"
            )
            bet_result: dict[str, Any] = {
                "bookmaker": bookmaker,
                "event": event,
                "outcome": outcome,
                "stake": stake,
                "odds": odds,
                "status": STATUS_SIMULATED,
                "ts": ts,
            }
        else:
            logger.warning(
                "[EXECUTOR] Попытка реального исполнения - "
                "live режим не реализован полностью"
            )
            bet_result = await self._place_bet(
                bookmaker, event, outcome, stake, odds
            )
            bet_result["ts"] = ts

        return bet_result

    async def _place_bet(
        self,
        bookmaker: str,
        event: str,
        outcome: str,
        stake: float,
        odds: float,
    ) -> dict[str, Any]:
        """Разместить реальную ставку (placeholder для будущей реализации).

        TODO: Интеграция с API каждого букмекера.
        """
        logger.warning(
            "[EXECUTOR] Реальное исполнение не реализовано: "
            "ставка %.2f @ %.2f на %s (%s)",
            stake, odds, outcome, bookmaker,
        )
        return {
            "bookmaker": bookmaker,
            "event": event,
            "outcome": outcome,
            "stake": stake,
            "odds": odds,
            "status": "NOT_IMPLEMENTED",
            "error": "Реальное исполнение не реализовано",
        }

    def get_active_bets(self) -> list[dict[str, Any]]:
        """Получить список неразрешённых ставок."""
        return [
            bet for bet in self._active_bets
            if bet.get("status") in (STATUS_PENDING, STATUS_PLACED, STATUS_SIMULATED)
        ]
