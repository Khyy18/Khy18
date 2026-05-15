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
from typing import Any, Optional

from arbitrage import config
from arbitrage.betfair_api import BetfairClient
from arbitrage import telegram_bot

logger = logging.getLogger(__name__)


# Статусы ставок
STATUS_PENDING = "PENDING"
STATUS_PLACED = "PLACED"
STATUS_CONFIRMED = "CONFIRMED"
STATUS_FAILED = "FAILED"
STATUS_SIMULATED = "SIMULATED"
STATUS_PARTIAL_FILL = "PARTIAL_FILL"
STATUS_NEEDS_HEDGE = "NEEDS_HEDGE"


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
            # Attempt Betfair lay hedge for successful legs
            try:
                if self.dry_run:
                    logger.warning(
                        "[EXECUTOR] PARTIAL_FILL: would attempt Betfair hedge for %s", event
                    )
                elif config.BETFAIR_APP_KEY:
                    for sleg in successful_legs:
                        if sleg.get("bookmaker") == "betfair" and sleg.get("bet_id"):
                            market_id = sleg.get("market_id")
                            selection_id = sleg.get("selection_id")
                            if not market_id or not selection_id:
                                logger.warning(
                                    "[EXECUTOR] Hedge: нет market_id/selection_id для %s", event
                                )
                                continue

                            # Get current market book for best lay price
                            hedge_client = BetfairClient()
                            try:
                                market_books = await hedge_client.list_market_book([market_id])
                                current_lay_price = None
                                if market_books:
                                    for runner in market_books[0].get("runners", []):
                                        if str(runner.get("selectionId")) == str(selection_id):
                                            lay_prices = runner.get("ex", {}).get("availableToLay", [])
                                            if lay_prices:
                                                current_lay_price = lay_prices[0].get("price")
                                            break

                                if current_lay_price is None:
                                    logger.warning(
                                        "[EXECUTOR] Hedge: не удалось получить текущую lay цену для %s",
                                        event,
                                    )
                                    continue

                                # Check if hedge loss exceeds 5% of stake
                                original_back_odds = sleg.get("odds", 0.0)
                                hedge_stake = sleg.get("stake", 0.0)
                                potential_loss_pct = (
                                    abs(1.0 - original_back_odds / current_lay_price) * 100.0
                                    if current_lay_price > 0
                                    else 0.0
                                )

                                if potential_loss_pct > 5.0:
                                    logger.warning(
                                        "[EXECUTOR] Hedge: убыток %.2f%% > 5%%, ручной хедж нужен для %s",
                                        potential_loss_pct, event,
                                    )
                                    try:
                                        import aiohttp as _aiohttp
                                        async with _aiohttp.ClientSession() as _sess:
                                            alert_text = (
                                                f"<b>HEDGE ALERT</b>\n"
                                                f"Event: {event}\n"
                                                f"Потенц. убыток: {potential_loss_pct:.2f}%\n"
                                                f"Текущая lay цена: {current_lay_price}\n"
                                                f"Ручной хедж нужен!"
                                            )
                                            await telegram_bot.send_message(_sess, alert_text)
                                    except Exception:
                                        pass
                                    continue

                                # Loss acceptable - place hedge at current market price
                                hedge_result = await self._place_bet(
                                    bookmaker="betfair",
                                    event=event,
                                    outcome=sleg.get("outcome", ""),
                                    stake=hedge_stake,
                                    odds=current_lay_price,
                                    selection_id=selection_id,
                                    market_id=market_id,
                                    side="LAY",
                                )
                                if hedge_result.get("status") == STATUS_PLACED:
                                    logger.info(
                                        "[EXECUTOR] Betfair LAY hedge успешен: %s @ %.2f",
                                        hedge_result.get("bet_id"), current_lay_price,
                                    )
                                else:
                                    logger.error(
                                        "[EXECUTOR] Betfair LAY hedge неудачен: %s",
                                        hedge_result.get("error", "unknown"),
                                    )
                            finally:
                                await hedge_client.close()
                else:
                    logger.warning(
                        "[EXECUTOR] PARTIAL_FILL: Betfair hedge невозможен (нет APP_KEY) для %s",
                        event,
                    )
            except Exception as hedge_exc:
                logger.error("[EXECUTOR] Betfair hedge failed: %s", hedge_exc)

            # If hedge fails or unavailable, mark as NEEDS_HEDGE and send urgent alert
            status = STATUS_NEEDS_HEDGE
            # Send Telegram alert (fire and forget pattern)
            try:
                import aiohttp as _aiohttp
                async with _aiohttp.ClientSession() as _sess:
                    alert_text = (
                        f"<b>URGENT: PARTIAL FILL</b>\n"
                        f"Event: {event}\n"
                        f"Failed legs: {failed_legs}\n"
                        f"Requires manual hedge!"
                    )
                    await telegram_bot.send_message(_sess, alert_text)
            except Exception:  # noqa: BLE001
                pass
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
        selection_id: Optional[str] = None,
        market_id: Optional[str] = None,
        side: str = "BACK",
    ) -> dict[str, Any]:
        """Разместить реальную ставку.

        Для Betfair: использует BetfairClient.place_orders если BETFAIR_APP_KEY задан.
        Для остальных букмекеров: placeholder (NOT_IMPLEMENTED).
        """
        # Betfair real placement
        if bookmaker == "betfair" and config.BETFAIR_APP_KEY and not self.dry_run:
            if not market_id or not selection_id:
                logger.warning(
                    "[EXECUTOR] Betfair: нет market_id или selection_id для %s",
                    outcome,
                )
                return {
                    "bookmaker": bookmaker,
                    "event": event,
                    "outcome": outcome,
                    "stake": stake,
                    "odds": odds,
                    "status": STATUS_FAILED,
                    "error": "market_id или selection_id не указан",
                }

            instruction: dict[str, Any] = {
                "selectionId": selection_id,
                "handicap": "0",
                "side": side,
                "orderType": "LIMIT",
                "limitOrder": {
                    "size": stake,
                    "price": odds,
                    "persistenceType": "LAPSE",
                },
            }

            max_attempts = 3
            client = BetfairClient()
            try:
                for attempt in range(max_attempts):
                    try:
                        result = await client.place_orders(market_id, [instruction])

                        if result.get("status") == "SUCCESS":
                            reports = result.get("instructionReports", [])
                            bet_id = ""
                            if reports:
                                bet_id = reports[0].get("betId", "")
                            logger.info(
                                "[EXECUTOR] Betfair ставка размещена: bet_id=%s %s %.2f @ %.2f",
                                bet_id, side, stake, odds,
                            )
                            return {
                                "bookmaker": bookmaker,
                                "event": event,
                                "outcome": outcome,
                                "stake": stake,
                                "odds": odds,
                                "status": STATUS_PLACED,
                                "bet_id": bet_id,
                                "market_id": market_id,
                                "selection_id": selection_id,
                            }
                        else:
                            error_code = result.get("errorCode", "UNKNOWN")
                            logger.warning(
                                "[EXECUTOR] Betfair ставка не принята (попытка %d/%d): %s",
                                attempt + 1, max_attempts, error_code,
                            )
                            if attempt < max_attempts - 1:
                                await asyncio.sleep(0.5 * (attempt + 1))
                                continue
                            return {
                                "bookmaker": bookmaker,
                                "event": event,
                                "outcome": outcome,
                                "stake": stake,
                                "odds": odds,
                                "status": STATUS_FAILED,
                                "error": f"Betfair отклонил: {error_code}",
                            }

                    except Exception as exc:
                        logger.error(
                            "[EXECUTOR] Betfair ошибка (попытка %d/%d): %s",
                            attempt + 1, max_attempts, exc,
                        )
                        if attempt < max_attempts - 1:
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        return {
                            "bookmaker": bookmaker,
                            "event": event,
                            "outcome": outcome,
                            "stake": stake,
                            "odds": odds,
                            "status": STATUS_FAILED,
                            "error": str(exc),
                        }
            finally:
                await client.close()

        # Fallback for non-betfair or missing config
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
