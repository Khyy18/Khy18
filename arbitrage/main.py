"""Главный модуль арбитражного бота.

Точка входа: запуск сканера, Telegram-бота и периодической статистики
через asyncio.gather. Graceful shutdown по SIGINT/SIGTERM.
"""

from __future__ import annotations

import asyncio
import logging
import random
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

import aiohttp

from arbitrage import config, memory
from arbitrage import telegram_bot
from arbitrage.ai_allocator import BankrollAllocator
from arbitrage.ai_batch import AiBatchScorer
from arbitrage.ai_bk_classifier import classifier_loop
from arbitrage.ai_correlation import correlation_loop
from arbitrage.ai_filter import ArbFilter
from arbitrage.ai_line_predictor import LinePredictor, compute_urgency_factor
from arbitrage.ai_news_scanner import news_scanner_loop
from arbitrage.ai_optimizer import optimizer_loop
from arbitrage.ai_rate_limiter import AiRateLimiter
from arbitrage.anti_ban import AntiBanEngine
from arbitrage.betfair_stream import market_maker_loop
from arbitrage.cashout import CashoutEngine
from arbitrage.clv_tracker import CLVTracker
from arbitrage.dedup import ArbDeduplicator
from arbitrage.executor import BetExecutor
from arbitrage.healthcheck import HealthcheckServer
from arbitrage.logging_config import setup_logging
from arbitrage.middles import MiddleScanner
from arbitrage.odds_api import OddsAPIClient
from arbitrage.pinnacle_api import PinnacleClient
from arbitrage.ranker import ArbRanker
from arbitrage.recheck import RecheckEngine
from arbitrage.scanner import ArbitrageScanner
from arbitrage.settlement import SettlementEngine
from arbitrage.steam_moves import SteamDetector
from arbitrage.supervisor import TaskSupervisor

logger = logging.getLogger(__name__)

# Модуль-уровневые объекты для дедупликации и синхронизации
_deduplicator: ArbDeduplicator = ArbDeduplicator()
_execution_lock: asyncio.Lock = asyncio.Lock()
_steam_detector: SteamDetector = SteamDetector()
_rate_limiter: AiRateLimiter = AiRateLimiter()
_clv_tracker: CLVTracker = CLVTracker()
_cashout_engine: CashoutEngine = CashoutEngine()

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
    ranker = ArbRanker(top_n=int(state.get("ranker_top_n", 10)))
    recheck_engine = RecheckEngine(session=session)
    last_quota_alert_time: float = 0.0

    logger.info("Цикл сканирования запущен")

    while True:
        try:
            # A2: Сброс override при новом месяце (квота обновляется 1-го числа)
            if state.get("scan_interval_override") and datetime.now(timezone.utc).day == 1:
                logger.info("Сброс scan_interval_override (1-е число месяца)")
                state.pop("scan_interval_override", None)

            sleep_interval = state.get("scan_interval_override", config.SCAN_INTERVAL_SEC)

            if not state.get("scanner_active", False):
                await asyncio.sleep(sleep_interval)
                continue

            # Fix 2: Сброс экспозиции на основе активных ставок в БД
            state["exposure"] = memory.get_active_exposure()

            # Fix 4: Проверка лимита экспозиции
            max_exposure = state.get("bankroll", 1000.0) * config.MAX_BANKROLL_EXPOSURE / 100.0
            if state.get("exposure", 0.0) >= max_exposure:
                logger.info("Достигнут лимит экспозиции, пропуск цикла")
                await asyncio.sleep(sleep_interval)
                continue

            # Fix 5: Проверка окна ставок
            start_h, end_h = anti_ban.get_betting_window()
            current_hour = datetime.now(timezone.utc).hour
            if not (start_h <= current_hour < end_h):
                logger.info("Вне окна ставок (%d:00-%d:00 UTC), пропуск", start_h, end_h)
                await asyncio.sleep(sleep_interval)
                continue

            logger.info("Сканирование начато: %s", datetime.now(timezone.utc).isoformat())
            scan_ts: float = time.time()

            # 1. Получить коэффициенты для всех спортов (параллельно)
            all_events: list[dict[str, Any]] = []
            tasks = [odds_client.get_odds(sport) for sport in config.SPORTS]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for sport, result in zip(config.SPORTS, results):
                if isinstance(result, Exception):
                    logger.error("Ошибка получения коэфф. %s: %s", sport, result)
                else:
                    all_events.extend(result)

            if not all_events:
                logger.info("Нет событий для анализа")
                await asyncio.sleep(sleep_interval)
                continue

            # 1a. Проверка здоровья API и алерт при проблемах
            api_health = odds_client.get_health()
            state["api_health"] = api_health
            remaining_q = api_health.get("remaining_quota")
            used_q = api_health.get("used_quota")
            latency_ms = api_health.get("last_latency_ms", 0.0)
            if remaining_q is not None and used_q is not None:
                total_q = remaining_q + used_q
                remaining_pct = (remaining_q / total_q * 100.0) if total_q > 0 else 100.0
            else:
                remaining_pct = 100.0

            # A2: Graceful degradation on quota exhaustion
            if remaining_pct < 5.0:
                state["scanner_active"] = False
                logger.error(
                    "Квота исчерпана (%.1f%%), сканер остановлен", remaining_pct
                )
                try:
                    await telegram_bot.send_quota_alert(session, remaining_pct, latency_ms)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Ошибка отправки quota-алерта: %s", exc)
                await asyncio.sleep(sleep_interval)
                continue
            elif remaining_pct < 20.0 and not state.get("scan_interval_override"):
                state["scan_interval_override"] = config.SCAN_INTERVAL_SEC * 2
                logger.warning(
                    "Квота < 20%% (%.1f%%), интервал сканирования удвоен до %d сек",
                    remaining_pct, config.SCAN_INTERVAL_SEC * 2,
                )

            if remaining_pct < 10.0 or latency_ms > 5000:
                now_ts = time.time()
                if now_ts - last_quota_alert_time >= 900.0:
                    last_quota_alert_time = now_ts
                    try:
                        await telegram_bot.send_quota_alert(session, remaining_pct, latency_ms)
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Ошибка отправки quota-алерта: %s", exc)

            # 2. Извлечь sharp-линии Pinnacle
            sharp_probs = PinnacleClient.extract_pinnacle_from_odds_api(all_events)

            # 3. Найти surebets и value bets
            surebets = scanner.find_surebets(all_events)
            value_bets = scanner.find_value_bets(all_events, sharp_probs)
            surebets_totals = scanner.find_surebets_totals(all_events)
            surebets_spreads = scanner.find_surebets_spreads(all_events)
            all_opps = surebets + value_bets + surebets_totals + surebets_spreads

            # Middles (коридоры)
            middle_scanner = MiddleScanner()
            middles_totals = middle_scanner.find_middles_totals(all_events)
            middles_spreads = middle_scanner.find_middles_spreads(all_events)
            middles_all = middles_totals + middles_spreads
            # Store raw middle opportunities for Telegram display
            state["middles_opps"] = middles_all[-10:]

            # Steam Moves
            _steam_detector.update_sharp_snapshot(all_events)
            steam_opps = _steam_detector.detect_steam(all_events, sharp_probs)
            state["steam_opps"] = steam_opps[-10:]

            # Cashout: проверяем PENDING ставки на возможность кэшаута
            try:
                pending_bets = memory.get_active_bets_for_cashout()
                # Преобразуем в формат, ожидаемый CashoutEngine
                pre_match_bets: list[dict[str, Any]] = []
                for bet in pending_bets:
                    if bet.get("event_id"):
                        pre_match_bets.append({
                            "event_id": bet["event_id"],
                            "event_name": bet.get("event", ""),
                            "bookmaker": bet.get("bookmaker", ""),
                            "outcome": bet.get("outcome", ""),
                            "odds": bet.get("odds", 0.0),
                            "stake": bet.get("stake", 0.0),
                            "placed_ts": bet.get("ts", ""),
                            "sport": bet.get("sport", ""),
                        })
                if pre_match_bets:
                    cashout_opps = _cashout_engine.find_cashout_opportunities(
                        pre_match_bets, all_events
                    )
                    state["cashout_opps"] = cashout_opps[-10:]
                    if cashout_opps:
                        logger.info("Cashout возможностей найдено: %d", len(cashout_opps))
            except Exception as exc:  # noqa: BLE001
                logger.error("Ошибка поиска cashout: %s", exc)

            if not all_opps:
                logger.info("Арбитражей не найдено")
                await asyncio.sleep(sleep_interval)
                continue

            logger.info("Найдено возможностей: %d", len(all_opps))

            # 4. AI Batch Scoring (вместо поштучной оценки)
            batch_scorer = AiBatchScorer()
            opp_dicts: list[dict[str, Any]] = []
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
                    "event_id": getattr(opp, "details", {}).get("event_id", getattr(opp, "event_id", "")),
                    "scan_timestamp": scan_ts,
                }
                opp_dicts.append(opp_dict)

            scored = await batch_scorer.score_batch(opp_dicts, session)

            # Merge AI scores back onto original opp_dicts by index
            for i, score_item in enumerate(scored):
                if i < len(opp_dicts):
                    opp_dicts[i]["ai_score"] = score_item.get("score", 50)
                    opp_dicts[i]["ai_reasoning"] = score_item.get("reasoning", "")

            filtered: list[dict[str, Any]] = []
            for opp_d in opp_dicts:
                ai_score = opp_d.get("ai_score", 0)
                if ai_score > 60:
                    # Fix 1: Для surebets - не используем Kelly, для value bets - sharp_prob
                    if opp_d.get("type") == "surebet":
                        opp_d["sizing_mode"] = "surebet"
                    else:
                        sharp_prob = opp_d.get("details", {}).get("sharp_prob", 0.5)
                        opp_d["win_prob"] = sharp_prob
                        opp_d["sizing_mode"] = "kelly"
                    opp_d["best_odds"] = opp_d["odds"][0] if opp_d.get("odds") else 2.0
                    filtered.append(opp_d)

            if not filtered:
                logger.info("После AI-фильтра кандидатов нет")
                await asyncio.sleep(sleep_interval)
                continue

            logger.info("Прошли AI-фильтр: %d", len(filtered))

            # 4a. LinePredictor: predict line movement for urgency
            line_predictor = LinePredictor()
            predictions_list: list[dict[str, Any]] = []
            _lp_degraded = False
            for opp in filtered:
                details = opp.get("details", {})
                velocity = details.get("line_velocity", 0.0)
                if velocity:
                    event_id = opp.get("event_id", "")
                    outcome = opp.get("event_name", "")
                    odds_val = opp.get("best_odds", 2.0)
                    sport = opp.get("sport", "")
                    commence_time = opp.get("commence_time", "")
                    # Estimate time_to_event in minutes
                    time_to_event_min = 60.0
                    if commence_time:
                        try:
                            ct = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
                            diff = (ct - datetime.now(timezone.utc)).total_seconds() / 60.0
                            if diff > 0:
                                time_to_event_min = diff
                        except (ValueError, TypeError):
                            pass
                    try:
                        prediction = await line_predictor.predict(
                            session, event_id, outcome, odds_val, velocity, sport, time_to_event_min
                        )
                        urgency_factor = compute_urgency_factor(prediction)
                        opp["urgency_factor"] = urgency_factor
                        prediction["event_id"] = event_id
                        predictions_list.append(prediction)
                        # Detect silent degradation: default values mean AI is unavailable
                        if prediction.get("direction") == "stable" and prediction.get("confidence", 0) == 0:
                            _lp_degraded = True
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("LinePredictor ошибка: %s", exc)

            if _lp_degraded:
                logger.debug("[SCANNER] LinePredictor: AI недоступен, urgency_factor = 1.0")

            # Store last 20 predictions in state
            state["line_predictions"] = predictions_list[-20:]

            # 4b. Ранжирование
            filtered = ranker.rank(filtered)
            logger.info("После ранжирования: %d", len(filtered))

            # 4b. Перепроверка коэффициентов (батчевая - один запрос на спорт)
            rechecked = await recheck_engine.recheck_batch(session, filtered)

            if not rechecked:
                logger.info("После recheck кандидатов нет")
                await asyncio.sleep(sleep_interval)
                continue

            logger.info("Прошли recheck: %d", len(rechecked))
            filtered = rechecked

            # 5. Аллокация банкролла
            bankroll = state.get("bankroll", 1000.0)
            try:
                allocations = await allocator.allocate(filtered, bankroll)
            except Exception as exc:  # noqa: BLE001
                logger.error("Ошибка аллокации: %s", exc)
                allocations = []

            # 6. Anti-ban проверки (расширенные)
            valid_allocations: list[dict[str, Any]] = []
            for alloc in allocations:
                opp = alloc.get("opportunity", {})
                bookmakers = opp.get("bookmakers", [])
                bm = bookmakers[0] if bookmakers else "unknown"
                event_id = opp.get("event", opp.get("event_name", "unknown"))

                # 6a. Проверка корреляции (букмекер + событие)
                if not anti_ban.check_correlation(bm, event_id):
                    logger.info("Корреляция: пропуск %s/%s", bm, event_id)
                    continue

                if not anti_ban.check_frequency(bm):
                    logger.info("Лимит ставок превышен для %s", bm)
                    continue

                # 6b. Адаптивная задержка по типу букмекера
                delay = anti_ban.get_adaptive_delay(bm)
                await asyncio.sleep(delay)

                # 6c. Гуманизация суммы ставки
                stake_amount = alloc.get("stake_amount", 0.0)
                if stake_amount > 0:
                    alloc["stake_amount"] = anti_ban.humanize_stake(stake_amount)

                # 6d. Детектирование пре-бана
                is_pre_ban, pre_ban_detail = anti_ban.detect_pre_ban(bm)
                if is_pre_ban:
                    logger.warning("Пре-бан детектирован для %s", bm)
                    try:
                        await telegram_bot.send_pre_ban_alert(session, bm, pre_ban_detail)
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Ошибка отправки pre-ban алерта: %s", exc)
                    continue

                valid_allocations.append(alloc)

            # 7. Исполнение (с дедупликацией и блокировкой)
            if valid_allocations:
                async with _execution_lock:
                    # Фильтрация дубликатов
                    unique_allocations: list[dict[str, Any]] = []
                    for alloc in valid_allocations:
                        opp = alloc.get("opportunity", {})
                        if _deduplicator.is_duplicate(opp):
                            logger.info(
                                "Дубликат пропущен: %s",
                                opp.get("event_name", opp.get("event", "")),
                            )
                            continue
                        unique_allocations.append(alloc)

                    if not unique_allocations:
                        logger.info("Все аллокации - дубликаты, пропуск")
                    else:
                        try:
                            results = await executor.execute(unique_allocations)
                        except Exception as exc:  # noqa: BLE001
                            logger.error("Ошибка исполнения: %s", exc)
                            results = []

                        # 8. Запись в память
                        for i, alloc in enumerate(unique_allocations):
                            opp = alloc.get("opportunity", {})
                            ai_score = opp.get("ai_score", 0)
                            # Fix 3: Корректный статус
                            status = "SIMULATED" if config.DRY_RUN else "PENDING"
                            # A3: pass event_id
                            opp_event_id = opp.get(
                                "event_id",
                                opp.get("details", {}).get("event_id", ""),
                            )
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
                                event_id=opp_event_id,
                            )

                            if i < len(results):
                                res = results[i]
                                # Record each leg separately for multi-leg surebets
                                if res.get("legs"):
                                    for leg_res in res["legs"]:
                                        memory.record_bet(
                                            arb_id=arb_id,
                                            bookmaker=leg_res.get("bookmaker", ""),
                                            event=res.get("event", ""),
                                            outcome=leg_res.get("outcome", ""),
                                            stake=leg_res.get("stake", 0.0),
                                            odds=leg_res.get("odds", 0.0),
                                            result=leg_res.get("status", "PENDING"),
                                        )
                                else:
                                    memory.record_bet(
                                        arb_id=arb_id,
                                        bookmaker=res.get("bookmaker", ""),
                                        event=res.get("event", ""),
                                        outcome=res.get("outcome", ""),
                                        stake=res.get("stake", 0.0),
                                        odds=res.get("odds", 0.0),
                                        result=res.get("status", "PENDING"),
                                    )

                            # Отмечаем как исполненные в дедупликаторе
                            _deduplicator.mark_executed(opp)

                            # CLV Tracking
                            if opp_event_id:
                                bet_odds = opp.get("best_odds", opp.get("odds", [2.0])[0] if opp.get("odds") else 2.0)
                                opp_outcome = opp.get("outcome", opp.get("selection", ""))
                                if not opp_outcome:
                                    # Попытка извлечь из details или первого leg
                                    opp_outcome = opp.get("details", {}).get("outcome", "")
                                _clv_tracker.record_bet_placement(
                                    arb_id, opp_event_id, bet_odds, opp.get("sport", ""),
                                    outcome=opp_outcome,
                                )

                            # Записываем в anti-ban
                            bookmakers = opp.get("bookmakers", [])
                            for bm in bookmakers:
                                anti_ban.record_bet(bm)
                                if config.DRY_RUN:
                                    simulated_duration = random.uniform(0.5, 2.0)
                                    anti_ban.record_acceptance_time(bm, simulated_duration)
                                elif i < len(results):
                                    real_duration = results[i].get(
                                        "acceptance_duration", 1.0
                                    )
                                    anti_ban.record_acceptance_time(bm, real_duration)

                            # 9. Telegram-алерт
                            if opp.get("profit_pct", 0.0) >= config.MIN_ARB_PROFIT:
                                try:
                                    await telegram_bot.send_arb_alert(
                                        session, opp, ai_score
                                    )
                                except Exception as exc:  # noqa: BLE001
                                    logger.error("Ошибка отправки алерта: %s", exc)

            logger.info("Цикл завершён. Исполнено: %d", len(valid_allocations))
            state["last_scan_ts"] = datetime.now(timezone.utc).isoformat()

        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Критическая ошибка в цикле: %s", exc)

        sleep_interval = state.get("scan_interval_override", config.SCAN_INTERVAL_SEC)
        await asyncio.sleep(sleep_interval)


async def stats_loop(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
    """Периодическое обновление статистики (каждый час)."""
    logger.info("Цикл статистики запущен")
    while True:
        try:
            await asyncio.sleep(3600)
            stats = memory.get_stats()
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            logger.info(
                "Обновление за %s: арбитражей=%d, ставок=%d, PnL=%.2f",
                today,
                stats.get("total_arbs", 0),
                stats.get("total_bets", 0),
                stats.get("total_pnl", 0.0),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка обновления статистики: %s", exc)


async def settlement_loop(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
    """Периодический расчёт ставок (каждые 30 мин) и обучение (раз в 24ч)."""
    logger.info("Цикл расчёта ставок запущен")
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
                # Обновление банкролла: только прибавляем PnL текущего цикла
                stats = memory.get_stats()
                total_pnl_now = stats.get("total_pnl", 0.0)
                pnl_before = state.get("_last_total_pnl", 0.0)
                settlement_pnl = total_pnl_now - pnl_before
                state["_last_total_pnl"] = total_pnl_now

                new_bankroll = state.get("bankroll", 1000.0) + settlement_pnl
                state["bankroll"] = new_bankroll
                memory.save_bankroll_state(new_bankroll)
            except Exception as exc:  # noqa: BLE001
                logger.error("Ошибка расчёта: %s", exc)

            # Обучение раз в 24 часа
            now = time.time()
            if now - last_learn_time >= learn_interval:
                try:
                    await engine.learn(session)
                    last_learn_time = now
                except Exception as exc:  # noqa: BLE001
                    logger.error("Ошибка обучения: %s", exc)

        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Критическая ошибка в settlement: %s", exc)


async def state_saver_loop(state: dict[str, Any]) -> None:
    """Периодическое сохранение состояния бота в БД (каждые 5 мин)."""
    logger.info("Цикл сохранения состояния запущен")
    while True:
        try:
            await asyncio.sleep(300)
            memory.save_bot_state("scanner_active", str(state.get("scanner_active", True)))
            override = state.get("scan_interval_override")
            if override is not None:
                memory.save_bot_state("scan_interval_override", str(override))
            else:
                memory.save_bot_state("scan_interval_override", "")
            # Persist bankroll so it survives crashes between settlement cycles
            bankroll = state.get("bankroll", 1000.0)
            memory.save_bot_state("bankroll", str(bankroll))
            logger.debug("Состояние сохранено в БД")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка сохранения состояния: %s", exc)


async def clv_check_loop(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
    """Периодическая проверка CLV (каждые 15 мин)."""
    logger.info("Цикл CLV-мониторинга запущен")
    while True:
        try:
            await asyncio.sleep(900)  # 15 мин
            await _clv_tracker.check_closing_lines(session)
            clv_stats = _clv_tracker.get_clv_stats()
            state["clv_stats"] = clv_stats
            if clv_stats.get("total_checked", 0) > 0:
                logger.info(
                    "CLV статистика: avg=%.2f%%, positive=%d, negative=%d",
                    clv_stats.get("avg_clv_pct", 0),
                    clv_stats.get("positive_count", 0),
                    clv_stats.get("negative_count", 0),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Ошибка CLV-мониторинга: %s", exc)


async def stream_arb_detector(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
    """Детектор арбитражей на основе Betfair streaming.

    При наличии BETFAIR_APP_KEY подписывается на market price changes.
    При изменении цены проверяет наличие арбитража с данными из последнего скана.
    """
    if not config.BETFAIR_APP_KEY:
        logger.info("[STREAM_ARB] BETFAIR_APP_KEY не задан, stream arb detector отключен")
        while True:
            await asyncio.sleep(3600)
        return

    from arbitrage.betfair_stream import BetfairStreamClient
    from arbitrage.scanner import ArbitrageScanner

    scanner = ArbitrageScanner()
    client = BetfairStreamClient()

    def on_price_change(data: dict[str, Any]) -> None:
        """Callback при изменении цены на Betfair."""
        market_id = data.get("market_id", "")
        runners = data.get("runners", [])

        # Store latest prices in state
        live_prices = state.setdefault("betfair_live_prices", {})
        live_prices[market_id] = {
            "runners": runners,
            "updated_ts": datetime.now(timezone.utc).isoformat(),
        }

        logger.debug(
            "[STREAM_ARB] Price change: market=%s, runners=%d",
            market_id, len(runners),
        )

    client.on_price_change(on_price_change)

    # Connect and keep alive with reconnection
    while True:
        try:
            await client.connect()
            logger.info("[STREAM_ARB] Betfair stream подключен, ожидание данных...")
            # Keep running while connected
            while client.connected:
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            await client.disconnect()
            raise
        except Exception as exc:
            logger.error("[STREAM_ARB] Ошибка stream: %s, переподключение через 30 сек", exc)
            await asyncio.sleep(30.0)


async def main() -> None:
    """Главная функция: инициализация и запуск всех циклов."""
    setup_logging()

    logger.info(BANNER)
    logger.info("Запуск: %s", datetime.now(timezone.utc).isoformat())
    logger.info("Режим: %s", "DRY RUN" if config.DRY_RUN else "LIVE")

    # Инициализация БД
    memory.init_db()

    # Валидация конфига
    warnings = _validate_config()
    for w in warnings:
        logger.warning("ВНИМАНИЕ: %s", w)

    # Состояние бота
    state: dict[str, Any] = {
        "scanner_active": True,
        "bankroll": 1000.0,
        "exposure": 0.0,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "middles_opps": [],
        "steam_opps": [],
        "cashout_opps": [],
        "clv_stats": {},
    }

    # A6: Загрузка состояния бота из БД (auto-recovery)
    saved_scanner_active = memory.load_bot_state("scanner_active")
    if saved_scanner_active is not None and saved_scanner_active != "":
        state["scanner_active"] = saved_scanner_active.lower() in ("true", "1", "yes")
        logger.info("scanner_active загружен из БД: %s", state["scanner_active"])

    saved_override = memory.load_bot_state("scan_interval_override")
    if saved_override is not None and saved_override != "":
        try:
            state["scan_interval_override"] = int(float(saved_override))
            logger.info("scan_interval_override загружен из БД: %s", saved_override)
        except (ValueError, TypeError):
            pass

    # Загрузка банкролла из БД (persistent)
    saved_bankroll = memory.load_bankroll_state()
    if saved_bankroll is not None:
        state["bankroll"] = saved_bankroll
        logger.info("Банкролл загружен из БД: %.2f", saved_bankroll)
    else:
        logger.info("Банкролл по умолчанию: 1000.0")

    # Инициализация базового PnL для корректного учёта в settlement_loop
    initial_stats = memory.get_stats()
    state["_last_total_pnl"] = initial_stats.get("total_pnl", 0.0)

    # Создание HTTP-сессии
    session = aiohttp.ClientSession()

    # Auto-discovery активных спортов
    try:
        odds_client_tmp = OddsAPIClient(session=session)
        discovered = await odds_client_tmp.discover_active_sports()
        if discovered:
            config.SPORTS = discovered
            logger.info("Auto-discovery: %d активных спортов", len(discovered))
        else:
            logger.info(
                "Auto-discovery не удалось, используем конфиг: %d спортов",
                len(config.SPORTS),
            )
    except Exception as exc:
        logger.error(
            "Auto-discovery ошибка: %s, используем конфиг: %d спортов",
            exc, len(config.SPORTS),
        )

    # Graceful shutdown
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Получен сигнал завершения. Остановка...")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows не поддерживает add_signal_handler
            pass

    # Healthcheck HTTP-сервер
    healthcheck = HealthcheckServer(state)
    await healthcheck.start()

    # Запуск через TaskSupervisor
    supervisor = TaskSupervisor()

    async def _state_saver_wrapper(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
        """Обёртка для state_saver_loop (не использует session)."""
        await state_saver_loop(state)

    task_factories: list[tuple[str, Any]] = [
        ("scanner", scanner_loop),
        ("telegram", telegram_bot.run_bot),
        ("stats", stats_loop),
        ("settlement", settlement_loop),
        ("state_saver", _state_saver_wrapper),
        ("news_scanner", news_scanner_loop),
        ("optimizer", optimizer_loop),
        ("classifier", classifier_loop),
        ("correlation", correlation_loop),
        ("market_maker", market_maker_loop),
        ("clv_check", clv_check_loop),
    ]

    # Betfair Stream Arb Detector (conditional)
    if config.BETFAIR_APP_KEY:
        task_factories.append(("stream_arb_detector", stream_arb_detector))

    try:
        await supervisor.run(task_factories, state, session)
    except asyncio.CancelledError:
        pass
    finally:
        await healthcheck.stop()
        await session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
