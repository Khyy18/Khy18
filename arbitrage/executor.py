"""Исполнитель ставок (executor).

В режиме DRY_RUN логирует намерения, не размещая реальные ставки.
Структура подготовлена для реального исполнения через API букмекеров.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from arbitrage import config


# Статусы ставок
STATUS_PENDING = "PENDING"
STATUS_PLACED = "PLACED"
STATUS_CONFIRMED = "CONFIRMED"
STATUS_FAILED = "FAILED"
STATUS_SIMULATED = "SIMULATED"


class BetExecutor:
    """Исполнитель ставок с поддержкой dry-run режима."""

    def __init__(self) -> None:
        self.dry_run: bool = config.DRY_RUN
        self._active_bets: list[dict[str, Any]] = []

    async def execute(self, allocations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Исполнить список аллокаций (ставок).

        В dry-run режиме логирует и возвращает статус SIMULATED.
        В реальном режиме (placeholder) пытается разместить ставки.

        Возвращает список результатов с полями:
          bookmaker, event, outcome, stake, odds, status, ts
        """
        results: list[dict[str, Any]] = []

        for alloc in allocations:
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
                # Реальное исполнение (placeholder)
                bet_result = await self._place_bet(
                    bookmaker, event, outcome, stake, odds
                )
                bet_result["ts"] = ts

            results.append(bet_result)
            self._active_bets.append(bet_result)

        return results

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
        print(
            f"[EXECUTOR] REAL BET: ставка {stake} @ {odds} "
            f"на {outcome} ({bookmaker}) - НЕ РЕАЛИЗОВАНО"
        )
        return {
            "bookmaker": bookmaker,
            "event": event,
            "outcome": outcome,
            "stake": stake,
            "odds": odds,
            "status": STATUS_FAILED,
            "error": "Реальное исполнение не реализовано",
        }

    def get_active_bets(self) -> list[dict[str, Any]]:
        """Получить список неразрешённых ставок."""
        return [
            bet for bet in self._active_bets
            if bet.get("status") in (STATUS_PENDING, STATUS_PLACED, STATUS_SIMULATED)
        ]
