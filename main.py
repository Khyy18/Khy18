"""Точка входа Zenith-Control Ultimate.

Запускает параллельно торговый цикл и Telegram-терминал в рамках ОДНОЙ
общей aiohttp.ClientSession и ОДНОГО общего состояния `state`.

Правила:
  - Весь тело торгового тика обёрнуто в try/except - транзиентные ошибки
    НИКОГДА не валят цикл, мы только логируем по-русски и спим до
    следующего тика.
  - Каждые 60 секунд: тянем свечи, считаем сигнал, при наличии сигнала
    спрашиваем ИИ, и только при APPROVE + confidence > 85 открываем сделку.
  - Перевод SL в безубыток при +1.0%, трейлинг TP при +1.5%.
  - Kill-switch: если суточный убыток достиг MAX_DAILY_LOSS - торговля
    ставится на паузу до ручного возобновления из Telegram.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

import ai_analyst
import api_engine
import config
import memory
import news_engine
import strategy
import telegram_bot


TICK_SECONDS = 60
CONFIDENCE_THRESHOLD = 85  # строгое «>», т.е. нужно минимум 86


async def _manage_open_trade(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    current_price: float,
) -> None:
    """Сопровождение открытой сделки: безубыток и трейлинг-TP."""
    trade = state.get("open_trade")
    if not trade:
        return
    entry = float(trade.get("entry") or 0.0)
    side = str(trade.get("side") or "").lower()
    if entry <= 0 or side not in ("long", "short", "buy", "sell"):
        return

    # Безубыток (+1.0%).
    if not trade.get("breakeven_done") and strategy.compute_breakeven(
        entry, current_price, side
    ):
        new_sl = entry
        resp = await api_engine.set_trading_stop(
            session, config.SYMBOL, stop_loss=new_sl
        )
        if resp and resp.get("retCode") == 0:
            trade["breakeven_done"] = True
            trade["sl"] = new_sl
            print(f"[LOOP] SL переведён в безубыток: {new_sl}")

    # Трейлинг-TP (+1.5%).
    new_trail = strategy.compute_trailing_tp(
        entry, current_price, trade.get("trail_tp"), side
    )
    if new_trail is not None and new_trail != trade.get("trail_tp"):
        resp = await api_engine.set_trading_stop(
            session, config.SYMBOL, take_profit=new_trail
        )
        if resp and resp.get("retCode") == 0:
            trade["trail_tp"] = new_trail
            print(f"[LOOP] Трейлинг-TP обновлён: {new_trail}")


async def _try_open_trade(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    signal: dict[str, Any],
) -> None:
    """Полный пайплайн входа: новости -> память -> ИИ-гейт -> ордер."""
    news = await news_engine.fetch_headlines(session)
    errors = memory.get_recent_errors(5)
    verdict = await ai_analyst.decide(session, signal, news, errors)
    print(
        f"[LOOP] ИИ-вердикт: {verdict.get('decision')} "
        f"(conf={verdict.get('confidence')}) reason={verdict.get('reason')}"
    )

    approved = (
        verdict.get("decision") == "APPROVE"
        and int(verdict.get("confidence", 0)) > CONFIDENCE_THRESHOLD
    )
    if not approved:
        memory.record_rejection(
            reason=str(verdict.get("reason", "")),
            confidence=int(verdict.get("confidence", 0)),
            ctx={
                "signal": signal.get("signal"),
                "reason": signal.get("reason"),
                "indicators": signal.get("indicators"),
                "entry": signal.get("entry"),
                "sl": signal.get("sl"),
                "tp": signal.get("tp"),
            },
        )
        state["last_rejection"] = {
            "reason": verdict.get("reason"),
            "confidence": verdict.get("confidence"),
            "signal": signal,
        }
        return

    # Рассчёт размера позиции по риску.
    balance = await api_engine.get_balance(session, "USDT")
    if balance is None or balance <= 0:
        print("[LOOP] Не удалось получить баланс - пропуск входа")
        return
    if state.get("equity_start") is None:
        state["equity_start"] = balance

    qty = strategy.position_size(
        equity=balance,
        entry=signal["entry"],
        stop_loss=signal["sl"],
        risk_per_trade=config.RISK_PER_TRADE,
    )
    if qty <= 0:
        print("[LOOP] Расчётный размер позиции 0 - пропуск входа")
        return

    side = "Buy" if signal["signal"] == "LONG" else "Sell"
    print(
        f"[LOOP] Открываем {side} {qty} {config.SYMBOL} @ ~{signal['entry']} "
        f"SL={signal['sl']} TP={signal['tp']}"
    )
    resp = await api_engine.place_order(
        session,
        symbol=config.SYMBOL,
        side=side,
        qty=qty,
        stop_loss=signal["sl"],
        take_profit=signal["tp"],
    )
    if not resp or resp.get("retCode") != 0:
        print(f"[LOOP] Не удалось разместить ордер: {resp}")
        return

    indicators = signal.get("indicators", {}) or {}
    trade_id = memory.record_trade(
        symbol=config.SYMBOL,
        side=signal["signal"],
        entry=signal["entry"],
        qty=qty,
        ema_val=indicators.get("ema200"),
        rsi_val=indicators.get("rsi"),
        atr_val=indicators.get("atr"),
        ai_reason=verdict.get("reason"),
        outcome="OPEN",
    )
    state["open_trade"] = {
        "id": trade_id,
        "side": signal["signal"],
        "entry": signal["entry"],
        "qty": qty,
        "sl": signal["sl"],
        "tp": signal["tp"],
        "breakeven_done": False,
        "trail_tp": None,
    }


async def _check_closed_trade(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
) -> None:
    """Если в локальном state есть open_trade, но на бирже позиции нет
    (SL/TP сработал) - фиксируем результат в SQLite."""
    trade = state.get("open_trade")
    if not trade:
        return
    positions = await api_engine.get_positions(session, config.SYMBOL)
    if positions:
        return  # ещё открыта

    # Позиция закрыта - оценим PnL по последнему close.
    klines = await api_engine.get_klines(session, config.SYMBOL, "1", 1)
    last_close = None
    if klines:
        try:
            last_close = float(klines[-1][4])
        except (IndexError, TypeError, ValueError):
            last_close = None
    if last_close is None:
        print("[LOOP] Не удалось определить цену закрытия - освобождаем state без записи")
        state["open_trade"] = None
        return

    entry = float(trade.get("entry") or 0.0)
    qty = float(trade.get("qty") or 0.0)
    side = str(trade.get("side") or "").upper()
    if side == "LONG":
        pnl = (last_close - entry) * qty
    else:
        pnl = (entry - last_close) * qty
    outcome = "WIN" if pnl > 0 else "LOSS"

    if trade.get("id"):
        memory.update_trade_outcome(int(trade["id"]), last_close, pnl, outcome)

    # Обновляем дневной PnL.
    state["daily_pnl"] = float(state.get("daily_pnl", 0.0) or 0.0) + pnl
    print(
        f"[LOOP] Сделка #{trade.get('id')} закрыта: {outcome} pnl={pnl:.4f} "
        f"daily_pnl={state['daily_pnl']:.4f}"
    )
    state["open_trade"] = None


async def trading_loop(
    state: dict[str, Any],
    session: aiohttp.ClientSession,
) -> None:
    """Бесконечный торговый цикл, тикающий раз в TICK_SECONDS."""
    print("[LOOP] Торговый цикл запущен")
    while True:
        try:
            # Сопровождение возможной открытой сделки, даже если бот на паузе.
            klines = await api_engine.get_klines(
                session, config.SYMBOL, "15", 250
            )
            if klines:
                try:
                    current_price = float(klines[-1][4])
                except (IndexError, TypeError, ValueError):
                    current_price = 0.0
                if state.get("open_trade") and current_price > 0:
                    await _manage_open_trade(session, state, current_price)
                await _check_closed_trade(session, state)

            # Kill-switch по дневному убытку.
            equity_start = state.get("equity_start")
            if equity_start and equity_start > 0:
                loss_pct = -float(state.get("daily_pnl", 0.0)) / float(equity_start)
                if loss_pct >= config.MAX_DAILY_LOSS and state.get("bot_running"):
                    state["bot_running"] = False
                    print(
                        f"[LOOP] Достигнут суточный лимит убытка "
                        f"({loss_pct*100:.2f}%). Торговля на паузе."
                    )
                    await telegram_bot.send_message(
                        session,
                        (
                            "🛑 Достигнут суточный лимит убытка "
                            f"{loss_pct*100:.2f}%. Торговля приостановлена."
                        ),
                        reply_markup=telegram_bot.set_keyboard(),
                    )

            # Поиск новых входов только если бот в активном режиме и нет открытой сделки.
            if (
                state.get("bot_running")
                and not state.get("open_trade")
                and klines
            ):
                signal = strategy.evaluate_signal(klines)
                if signal.get("signal"):
                    print(
                        f"[LOOP] Технический сигнал {signal['signal']}: "
                        f"{signal.get('reason')}"
                    )
                    await _try_open_trade(session, state, signal)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            # Никогда не даём циклу умереть от транзиентной ошибки.
            print(f"[LOOP] Транзиентная ошибка тика: {exc}")

        await asyncio.sleep(TICK_SECONDS)


async def main() -> None:
    missing = config.validate_config()
    if missing:
        print(
            "[MAIN] Отсутствуют обязательные переменные окружения: "
            + ", ".join(missing)
        )
        print("[MAIN] Заполните .env (см. .env.example) и перезапустите бота")
        return

    memory.init_db()

    state: dict[str, Any] = {
        "bot_running": True,
        "daily_pnl": 0.0,
        "equity_start": None,
        "open_trade": None,
        "last_rejection": None,
    }

    async with aiohttp.ClientSession() as session:
        print("[MAIN] Zenith-Control Ultimate запущен")
        # --- Проверка авторизации на Bybit (запрос баланса) ---
        try:
            balance = await api_engine.get_balance(session, "USDT")
        except Exception as exc:  # noqa: BLE001
            balance = None
            print(f"[MAIN] Ошибка при проверке авторизации Bybit: {exc}")

        if balance is None:
            print(
                "[MAIN] Не удалось авторизоваться на Bybit: "
                "проверьте BYBIT_API_KEY/BYBIT_API_SECRET и режим (testnet/mainnet)."
            )
        else:
            mode = "TESTNET" if config.IS_TESTNET else "MAINNET"
            print(
                f"[MAIN] Успех авторизации на Bybit ({mode}). "
                f"Баланс USDT: {balance:.4f}"
            )
            state["equity_start"] = balance

        print("[MAIN] Telegram-бот запущен в режиме Long Polling")
        await telegram_bot.send_message(
            session,
            "🚀 <b>Zenith-Control Ultimate</b> запущен.\nВыберите действие ниже.",
            reply_markup=telegram_bot.set_keyboard(),
        )
        await asyncio.gather(
            trading_loop(state, session),
            telegram_bot.run_bot(state, session),
        )


if __name__ == "__main__":
    asyncio.run(main())
