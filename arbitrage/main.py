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
from arbitrage.ranker import ArbRanker
from arbitrage.recheck import RecheckEngine
from arbitrage.scanner import ArbitrageScanner
from arbitrage.settlement import SettlementEngine

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

            # Fix 2: Сброс экспозиции на основе активных ставок в БД
            state["exposure"] = memory.get_active_exposure()

            # Fix 4: Проверка лимита экспозиции
            max_exposure = state.get("bankroll", 1000.0) * config.MAX_BANKROLL_EXPOSURE / 100.0
            if state.get("exposure", 0.0) >= max_exposure:
                print("[SCANNER] Достигнут лимит экспозиции, пропуск цикла")
                await asyncio.sleep(config.SCAN_INTERVAL_SEC)
                continue

            # Fix 5: Проверка окна ставок
            start_h, end_h = anti_ban.get_betting_window()
            current_hour = datetime.now(timezone.utc).hour
            if not (start_h <= current_hour < end_h):
                print(f"[SCANNER] Вне окна ставок ({start_h}:00-{end_h}:00 UTC), пропуск")
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
            surebets_totals = scanner.find_surebets_totals(all_events)
            surebets_spreads = scanner.find_surebets_spreads(all_events)
            all_opps = surebets + value_bets + surebets_totals + surebets_spreads

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
                    "details": getattr(opp, "details", {}),
                    "commence_time": getattr(opp, "details", {}).get("commence_time", ""),
                }
                try:
                    evaluation = await ai_filter.evaluate(opp_dict)
                except Exception as exc:  # noqa: BLE001
                    print(f"[SCANNER] Ошибка AI-фильтра: {exc}")
                    evaluation = {"score": 50, "is_live": False}

                ai_score = evaluation.get("score", 50)
                if ai_score > 60:
                    opp_dict["ai_score"] = ai_score
                    # Fix 1: Для surebets - не используем Kelly, для value bets - sharp_prob
                    if opp_dict["type"] == "surebet":
                        # Surebets: размер по profit_pct, не Kelly
                        opp_dict["sizing_mode"] = "surebet"
                    else:
                        # Value bets: используем sharp_prob как win_prob
                        sharp_prob = opp_dict.get("details", {}).get("sharp_prob", 0.5)
                        opp_dict["win_prob"] = sharp_prob
                        opp_dict["sizing_mode"] = "kelly"
                    opp_dict["best_odds"] = opp.odds[0] if opp.odds else 2.0
                    filtered.append(opp_dict)

            if not filtered:
                print("[SCANNER] После AI-фильтра кандидатов нет")
                await asyncio.sleep(config.SCAN_INTERVAL_SEC)
                continue

            print(f"[SCANNER] Прошли AI-фильтр: {len(filtered)}")

            # 4a. Ранжирование
            ranker = ArbRanker(top_n=int(state.get("ranker_top_n", 10)))
            filtered = ranker.rank(filtered)
            print(f"[SCANNER] После ранжирования: {len(filtered)}")

            # 4b. Перепроверка коэффициентов
            recheck_engine = RecheckEngine(session=session)
            rechecked: list[dict[str, Any]] = []
            for opp_dict in filtered:
                try:
                    alive = await recheck_engine.recheck_opportunity(session, opp_dict)
                    if alive:
                        rechecked.append(opp_dict)
                except Exception as exc:  # noqa: BLE001
                    print(f"[SCANNER] Ошибка recheck: {exc}")
                    rechecked.append(opp_dict)

            if not rechecked:
                print("[SCANNER] После recheck кандидатов нет")
                await asyncio.sleep(config.SCAN_INTERVAL_SEC)
                continue

            print(f"[SCANNER] Прошли recheck: {len(rechecked)}")
            filtered = rechecked

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
                    # Fix 3: Корректный статус
                    status = "SIMULATED" if config.DRY_RUN else "PENDING"
                    arb_id = memory.record_arb(
                        sport=opp.get("sport", ""),
                        event=opp.get("event", ""),
                        arb_type=opp.get("type", "surebet"),
                        bookmakers=opp.get("bookmakers", []),
                        odds={"odds": opp.get("odds", [])},
                        profit_pct=opp.get("profit_pct", 0.0),
                        edge_pct=opp.get("edge_pct", 0.0),
                        ai_score=ai_score,
                        status=status,
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


async def settlement_loop(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
    """Периодический расчёт ставок (каждые 30 мин) и обучение (раз в 24ч)."""
    print("[SETTLEMENT] Цикл расчёта ставок запущен")
    engine = SettlementEngine()
    last_learn_time: float = 0.0
    learn_interval: float = 86400.0  # 24 часа
    settle_interval: float = 1800.0  # 30 минут

    while True:
        try:
            await asyncio.sleep(settle_interval)

            # Расчёт ставок
            try:
                await engine.settle_bets(session)
            except Exception as exc:  # noqa: BLE001
                print(f"[SETTLEMENT] Ошибка расчёта: {exc}")

            # Обучение раз в 24 часа
            now = time.time()
            if now - last_learn_time >= learn_interval:
                try:
                    await engine.learn(session)
                    last_learn_time = now
                except Exception as exc:  # noqa: BLE001
                    print(f"[SETTLEMENT] Ошибка обучения: {exc}")

        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[SETTLEMENT] Критическая ошибка: {exc}")


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
        asyncio.create_task(settlement_loop(state, session)),
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
