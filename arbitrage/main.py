"""Главный модуль арбитражного бота.

Точка входа: запуск сканера, Telegram-бота и периодической статистики
через asyncio.gather. Graceful shutdown по SIGINT/SIGTERM.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

import aiohttp

from arbitrage import config, memory
from arbitrage import telegram_bot
from arbitrage.ai_allocator import BankrollAllocator
from arbitrage.ai_filter import ArbFilter
from arbitrage.anti_ban import AntiBanEngine
from arbitrage.executor import BetExecutor
from arbitrage.odds_api import OddsAPIClient
from arbitrage.pinnacle_api import PinnacleClient
from arbitrage.scanner import ArbitrageScanner

logger = logging.getLogger(__name__)

BANNER = """
╔══════════════════════════════════════════╗
║   ARBITRAGE BOT v1.0                     ║
║   Арбитражный бот для спортивных ставок  ║
║   с ИИ-фильтрацией и Kelly-аллокацией   ║
╚══════════════════════════════════════════╝
"""


def _validate_config() -> list[str]:
    """Проверить наличие обязательных переменных окружения."""
    warnings: list[str] = []
    if not config.ODDS_API_KEY:
        warnings.append("ODDS_API_KEY не задан")
    if not config.TELEGRAM_TOKEN:
        warnings.append("TELEGRAM_TOKEN не задан")
    if not config.TELEGRAM_CHAT_ID:
        warnings.append("TELEGRAM_CHAT_ID не задан")
    if not config.GROQ_API_KEY:
        warnings.append("GROQ_API_KEY не задан (AI-фильтр будет недоступен)")
    return warnings


async def scanner_loop(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
    """Периодический цикл сканирования арбитражей."""
    odds_client = OddsAPIClient(session=session)
    pinnacle_client = PinnacleClient(session=session)
    scanner = ArbitrageScanner()
    ai_filter = ArbFilter(session=session)
    allocator = BankrollAllocator(session=session, bankroll=state.get("bankroll", 1000.0))
    executor = BetExecutor()
    anti_ban = AntiBanEngine()

    print("[SCANNER] Цикл сканирования запущен")

    while True:
        try:
            if not state.get("scanner_active", False):
                await asyncio.sleep(config.SCAN_INTERVAL_SEC)
                continue

            print(f"[SCANNER] Сканирование начато: {datetime.now(timezone.utc).isoformat()}")

            # 1. Получить коэффициенты для всех спортов
            all_events: list[dict[str, Any]] = []
            for sport in config.SPORTS:
                try:
                    events = await odds_client.get_odds(sport)
                    all_events.extend(events)
                except Exception as exc:  # noqa: BLE001
                    print(f"[SCANNER] Ошибка получения коэфф. {sport}: {exc}")

            if not all_events:
                print("[SCANNER] Нет событий для анализа")
                await asyncio.sleep(config.SCAN_INTERVAL_SEC)
                continue

            # 2. Извлечь sharp-линии Pinnacle
            sharp_probs = PinnacleClient.extract_pinnacle_from_odds_api(all_events)

            # 3. Найти surebets и value bets
            surebets = scanner.find_surebets(all_events)
            value_bets = scanner.find_value_bets(all_events, sharp_probs)
            all_opps = surebets + value_bets

            if not all_opps:
                print("[SCANNER] Арбитражей не найдено")
                await asyncio.sleep(config.SCAN_INTERVAL_SEC)
                continue

            print(f"[SCANNER] Найдено возможностей: {len(all_opps)}")

            # 4. AI-фильтрация
            filtered: list[dict[str, Any]] = []
            for opp in all_opps:
                opp_dict: dict[str, Any] = {
                    "sport": opp.sport,
                    "event": opp.event_name,
                    "bookmakers": opp.bookmakers,
                    "odds": opp.odds,
                    "profit_pct": opp.profit_pct,
                    "edge_pct": opp.edge_pct,
                    "type": opp.type,
                    "home": opp.home,
                    "away": opp.away,
                    "event_name": opp.event_name,
                }
                try:
                    evaluation = await ai_filter.evaluate(opp_dict)
                except Exception as exc:  # noqa: BLE001
                    print(f"[SCANNER] Ошибка AI-фильтра: {exc}")
                    evaluation = {"score": 50, "is_live": False}

                ai_score = evaluation.get("score", 50)
                if ai_score > 60:
                    opp_dict["ai_score"] = ai_score
                    opp_dict["win_prob"] = ai_score / 100.0
                    opp_dict["best_odds"] = opp.odds[0] if opp.odds else 2.0
                    filtered.append(opp_dict)

            if not filtered:
                print("[SCANNER] После AI-фильтра кандидатов нет")
                await asyncio.sleep(config.SCAN_INTERVAL_SEC)
                continue

            print(f"[SCANNER] Прошли AI-фильтр: {len(filtered)}")

            # 5. Аллокация банкролла
            bankroll = state.get("bankroll", 1000.0)
            try:
                allocations = await allocator.allocate(filtered, bankroll)
            except Exception as exc:  # noqa: BLE001
                print(f"[SCANNER] Ошибка аллокации: {exc}")
                allocations = []

            # 6. Anti-ban проверки
            valid_allocations: list[dict[str, Any]] = []
            for alloc in allocations:
                opp = alloc.get("opportunity", {})
                bookmakers = opp.get("bookmakers", [])
                bm = bookmakers[0] if bookmakers else "unknown"

                if not anti_ban.check_frequency(bm):
                    print(f"[SCANNER] Лимит ставок превышен для {bm}")
                    continue

                delay = anti_ban.should_delay()
                await asyncio.sleep(delay)
                valid_allocations.append(alloc)

            # 7. Исполнение
            if valid_allocations:
                try:
                    results = await executor.execute(valid_allocations)
                except Exception as exc:  # noqa: BLE001
                    print(f"[SCANNER] Ошибка исполнения: {exc}")
                    results = []

                # 8. Запись в память
                for i, alloc in enumerate(valid_allocations):
                    opp = alloc.get("opportunity", {})
                    ai_score = opp.get("ai_score", 0)
                    arb_id = memory.record_arb(
                        sport=opp.get("sport", ""),
                        event=opp.get("event", ""),
                        arb_type=opp.get("type", "surebet"),
                        bookmakers=opp.get("bookmakers", []),
                        odds={"odds": opp.get("odds", [])},
                        profit_pct=opp.get("profit_pct", 0.0),
                        edge_pct=opp.get("edge_pct", 0.0),
                        ai_score=ai_score,
                        status="EXECUTED" if config.DRY_RUN else "EXECUTED",
                    )

                    if i < len(results):
                        res = results[i]
                        memory.record_bet(
                            arb_id=arb_id,
                            bookmaker=res.get("bookmaker", ""),
                            event=res.get("event", ""),
                            outcome=res.get("outcome", ""),
                            stake=res.get("stake", 0.0),
                            odds=res.get("odds", 0.0),
                            result=res.get("status", "PENDING"),
                        )

                    # Записываем в anti-ban
                    bookmakers = opp.get("bookmakers", [])
                    for bm in bookmakers:
                        anti_ban.record_bet(bm)

                    # 9. Telegram-алерт
                    if opp.get("profit_pct", 0.0) >= config.MIN_ARB_PROFIT:
                        try:
                            await telegram_bot.send_arb_alert(
                                session, opp, ai_score
                            )
                        except Exception as exc:  # noqa: BLE001
                            print(f"[SCANNER] Ошибка отправки алерта: {exc}")

                # Обновить экспозицию
                total_staked = sum(
                    a.get("stake_amount", 0.0) for a in valid_allocations
                )
                state["exposure"] = state.get("exposure", 0.0) + total_staked

            print(f"[SCANNER] Цикл завершён. Исполнено: {len(valid_allocations)}")

        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[SCANNER] Критическая ошибка в цикле: {exc}")

        await asyncio.sleep(config.SCAN_INTERVAL_SEC)


async def stats_loop(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
    """Периодическое обновление статистики (каждый час)."""
    print("[STATS] Цикл статистики запущен")
    while True:
        try:
            await asyncio.sleep(3600)
            stats = memory.get_stats()
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            print(
                f"[STATS] Обновление за {today}: "
                f"арбитражей={stats.get('total_arbs', 0)}, "
                f"ставок={stats.get('total_bets', 0)}, "
                f"PnL={stats.get('total_pnl', 0.0):.2f}"
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[STATS] Ошибка обновления статистики: {exc}")


async def main() -> None:
    """Главная функция: инициализация и запуск всех циклов."""
    print(BANNER)
    print(f"[MAIN] Запуск: {datetime.now(timezone.utc).isoformat()}")
    print(f"[MAIN] Режим: {'DRY RUN' if config.DRY_RUN else 'LIVE'}")

    # Инициализация БД
    memory.init_db()

    # Валидация конфига
    warnings = _validate_config()
    for w in warnings:
        print(f"[MAIN] ВНИМАНИЕ: {w}")

    # Состояние бота
    state: dict[str, Any] = {
        "scanner_active": True,
        "bankroll": 1000.0,
        "exposure": 0.0,
        "start_time": datetime.now(timezone.utc).isoformat(),
    }

    # Создание HTTP-сессии
    session = aiohttp.ClientSession()

    # Graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        print("\n[MAIN] Получен сигнал завершения. Остановка...")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows не поддерживает add_signal_handler
            pass

    # Запуск параллельных задач
    tasks = [
        asyncio.create_task(scanner_loop(state, session)),
        asyncio.create_task(telegram_bot.run_bot(state, session)),
        asyncio.create_task(stats_loop(state, session)),
    ]

    try:
        # Ждём сигнал завершения или завершения задач
        done, pending = await asyncio.wait(
            tasks + [asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        # Отмена всех задач
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await session.close()
        print("[MAIN] Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
