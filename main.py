"""Точка входа Zenith-Control Ultimate v2.

Запускает параллельно многосимвольный торговый цикл и Telegram-терминал
в рамках ОДНОЙ общей aiohttp.ClientSession и ОДНОГО общего состояния
`state` с разделением global / per-symbol.

Ключевые принципы:
  - Решения о входе принимает strategy_v2 (детерминированный Donchian +
    мультитаймфреймовый фильтр). ИИ-модули (ai_macro_sentinel, ai_regime,
    ai_postmortem) подмешиваются через расписания тиков и пишут только
    в blackout / regime / еженедельный отчёт.
  - Весь тик обёрнут в try/except. Транзиентные ошибки НИКОГДА не валят
    цикл, мы только логируем по-русски и спим до следующего тика.
  - Ярусные kill-switches: DAILY (3%), WEEKLY (7%), MDD (15%). Daily
    снимается на границе UTC-суток, WEEKLY через 7 дней от триггера,
    MDD только вручную через Telegram.
  - Риск на сделку ограничен config.RISK_PER_TRADE, суммарно открытый
    риск по портфелю ограничен config.GLOBAL_RISK_CAP.
"""

from __future__ import annotations

import asyncio
import collections
import math
import statistics
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiohttp

import ai_macro_sentinel
import ai_postmortem
import ai_regime
import api_engine  # noqa: F401  # legacy shim, поддерживается для совместимости
import config
import memory
import news_engine
import strategy_v2
import telegram_bot
from exchanges import get_adapter


TICK_SECONDS = 60

# Единый адаптер биржи выбирается через config.EXCHANGE (env EXCHANGE).
# Все дальнейшие вызовы идут через него - переключение Bybit/OKX/etc
# сводится к смене переменной окружения.
EXCHANGE = get_adapter(config.EXCHANGE)


# --- Время / ISO помощники -------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _from_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _floor_utc_midnight(dt: datetime) -> datetime:
    d = dt.astimezone(timezone.utc)
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def _next_utc_midnight(dt: datetime) -> datetime:
    return _floor_utc_midnight(dt) + timedelta(days=1)


def _iso_week_key(dt: datetime) -> str:
    y, w, _ = dt.astimezone(timezone.utc).isocalendar()
    return f"{y}-W{w:02d}"


def _iso_week_start(dt: datetime) -> datetime:
    d = dt.astimezone(timezone.utc)
    # weekday(): Monday = 0 ... Sunday = 6
    monday = _floor_utc_midnight(d) - timedelta(days=d.weekday())
    return monday


def _format_duration(start_iso: Optional[str], end: datetime) -> str:
    """Вернуть длительность 'Xч Yм' или 'Xд Yч' между start_iso и end.
    Используется в push-уведомлениях о закрытии позиций. На невалидный ISO
    возвращает '-' и не падает."""
    start = _from_iso(start_iso)
    if start is None:
        return "-"
    secs = int((end - start).total_seconds())
    if secs < 60:
        return f"{secs}с"
    hours, rem = divmod(secs, 3600)
    minutes, _ = divmod(rem, 60)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days}д {hours}ч"
    return f"{hours}ч {minutes}м"


# --- Роллинг суточных / недельных якорей ----------------------------------

def _roll_daily_weekly_anchors(state: dict[str, Any], now: datetime) -> None:
    g = state["global"]

    # Суточный якорь.
    anchor_daily = _from_iso(g.get("daily_anchor_iso"))
    if anchor_daily is None or anchor_daily.date() < now.date():
        if anchor_daily is not None:
            print(f"[LOOP] Суточный якорь сброшен: {g.get('daily_pnl', 0.0)} -> 0.0")
        g["daily_pnl"] = 0.0
        g["daily_anchor_iso"] = _iso(_floor_utc_midnight(now))

    # Недельный якорь (ISO-неделя по UTC).
    anchor_weekly = _from_iso(g.get("weekly_anchor_iso"))
    current_week = _iso_week_key(now)
    if anchor_weekly is None or _iso_week_key(anchor_weekly) != current_week:
        if anchor_weekly is not None:
            print(f"[LOOP] Недельный якорь сброшен: {g.get('weekly_pnl', 0.0)} -> 0.0")
        g["weekly_pnl"] = 0.0
        g["weekly_anchor_iso"] = _iso(_iso_week_start(now))


# --- Kill-switches ---------------------------------------------------------

def _reset_kill_switches_if_due(state: dict[str, Any], now: datetime) -> None:
    g = state["global"]
    ks = g.get("kill_switch_state", "NONE")
    until = _from_iso(g.get("kill_until_utc"))

    if ks == "DAILY" and until is not None and now >= until:
        print("[KILL] Суточный kill-switch снят по расписанию")
        g["kill_switch_state"] = "NONE"
        g["kill_until_utc"] = None
        g["kill_detail"] = ""
        return

    if ks == "WEEKLY" and until is not None and now >= until:
        print("[KILL] Недельный kill-switch снят по расписанию")
        g["kill_switch_state"] = "NONE"
        g["kill_until_utc"] = None
        g["kill_detail"] = ""
        return

    # MDD не снимается автоматически - только через Telegram-кнопку.


async def _notify_kill(
    session: aiohttp.ClientSession,
    text: str,
) -> None:
    try:
        await telegram_bot.send_message(
            session, text, reply_markup=telegram_bot.set_keyboard()
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[KILL] Не удалось отправить уведомление: {exc}")


async def _apply_kill_switches(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    now: datetime,
) -> None:
    g = state["global"]
    equity_start = float(g.get("equity_start") or 0.0)
    if equity_start <= 0:
        return

    ks_before = g.get("kill_switch_state", "NONE")

    # DAILY: loss_pct >= MAX_DAILY_LOSS, только из NONE.
    daily_pnl = float(g.get("daily_pnl", 0.0) or 0.0)
    if daily_pnl < 0 and ks_before == "NONE":
        loss_ratio = -daily_pnl / equity_start
        if loss_ratio >= float(config.MAX_DAILY_LOSS):
            until = _next_utc_midnight(now)
            detail = (
                f"Суточный убыток {loss_ratio * 100:.2f}% превысил лимит "
                f"{config.MAX_DAILY_LOSS * 100:.2f}%. Пауза до {_iso(until)}."
            )
            g["kill_switch_state"] = "DAILY"
            g["kill_until_utc"] = _iso(until)
            g["kill_detail"] = detail
            print(f"[KILL] DAILY активирован: {detail}")
            await _notify_kill(session, f"🛑 <b>DAILY kill-switch</b>\n{detail}")
            ks_before = "DAILY"

    # WEEKLY: loss_pct >= MAX_WEEKLY_LOSS, из NONE или DAILY.
    weekly_pnl = float(g.get("weekly_pnl", 0.0) or 0.0)
    if weekly_pnl < 0 and ks_before in ("NONE", "DAILY"):
        loss_ratio = -weekly_pnl / equity_start
        if loss_ratio >= float(config.MAX_WEEKLY_LOSS):
            until = now + timedelta(days=7)
            detail = (
                f"Недельный убыток {loss_ratio * 100:.2f}% превысил лимит "
                f"{config.MAX_WEEKLY_LOSS * 100:.2f}%. Пауза до {_iso(until)}."
            )
            g["kill_switch_state"] = "WEEKLY"
            g["kill_until_utc"] = _iso(until)
            g["kill_detail"] = detail
            print(f"[KILL] WEEKLY активирован: {detail}")
            await _notify_kill(session, f"🛑 <b>WEEKLY kill-switch</b>\n{detail}")
            ks_before = "WEEKLY"

    # MDD: по текущей просадке от HWM.
    try:
        current_dd = float(memory.get_current_drawdown() or 0.0)
    except Exception as exc:  # noqa: BLE001
        print(f"[KILL] Ошибка чтения просадки: {exc}")
        current_dd = 0.0
    if current_dd >= float(config.MAX_DRAWDOWN) and ks_before != "MDD":
        detail = (
            f"Просадка {current_dd * 100:.2f}% превысила лимит "
            f"{config.MAX_DRAWDOWN * 100:.2f}%. Снятие только вручную."
        )
        g["kill_switch_state"] = "MDD"
        g["kill_until_utc"] = None
        g["kill_detail"] = detail
        print(f"[KILL] MDD активирован: {detail}")
        await _notify_kill(
            session,
            "🛡 <b>MDD kill-switch</b>\n" + detail,
        )


# --- Equity / HWM ---------------------------------------------------------

# cumulative_pnl - кумулятивный PnL за всё время работы процесса.
# НЕ сбрасывается при ротации daily/weekly. Используется для снимка эквити
# и расчёта просадки (MDD). weekly_pnl используется только для WEEKLY kill-switch.

def _record_equity_snapshot(state: dict[str, Any], equity: float) -> None:
    g = state["global"]
    prev_hwm = float(g.get("hwm") or 0.0)
    hwm = max(prev_hwm, float(equity))
    drawdown = (hwm - float(equity)) / hwm if hwm > 0 else 0.0
    g["hwm"] = hwm
    try:
        memory.record_equity(float(equity), hwm, drawdown)
    except Exception as exc:  # noqa: BLE001
        print(f"[LOOP] Ошибка record_equity: {exc}")


# --- AI тикеры ------------------------------------------------------------

async def _hourly_macro_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    now: datetime,
) -> None:
    g = state["global"]
    last_epoch = float(g.get("last_macro_check_epoch") or 0.0)
    first_run = g.get("blackout", {}).get("ts") is None
    if not first_run and (time.time() - last_epoch) < 3600.0:
        return
    try:
        decision = await ai_macro_sentinel.check(session)
    except Exception as exc:  # noqa: BLE001
        print(f"[AI] macro-sentinel: ошибка вызова: {exc}")
        return
    if isinstance(decision, dict):
        g["blackout"] = {
            "blackout": bool(decision.get("blackout")),
            "until_utc": decision.get("until_utc"),
            "reason": str(decision.get("reason", "") or ""),
            "ts": decision.get("ts") or _iso(now),
        }
        g["last_macro_check_epoch"] = time.time()
        state_bo = "ON" if g["blackout"]["blackout"] else "OFF"
        print(
            f"[AI] macro-sentinel: blackout={state_bo} "
            f"reason={g['blackout']['reason']} until={g['blackout']['until_utc']}"
        )


async def _regime_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    symbol: str,
    now: datetime,
) -> None:
    sym_state = state["symbols"][symbol]
    last_epoch = float(sym_state.get("last_regime_check_epoch") or 0.0)
    if (time.time() - last_epoch) < float(config.AI_REGIME_TTL_SEC):
        return

    # Дневные свечи.
    try:
        raw_d = await EXCHANGE.get_klines(session, symbol, interval="D", limit=45)
    except Exception as exc:  # noqa: BLE001
        print(f"[AI] regime {symbol}: ошибка get_klines(D): {exc}")
        return
    if not raw_d:
        return
    daily_ohlc: list[dict[str, Any]] = []
    for k in raw_d:
        try:
            daily_ohlc.append(
                {
                    "ts": int(k[0]),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                }
            )
        except (IndexError, TypeError, ValueError):
            continue

    # Часовые свечи для ATR(1h).
    try:
        raw_1h = await EXCHANGE.get_klines(session, symbol, interval="60", limit=50)
    except Exception as exc:  # noqa: BLE001
        print(f"[AI] regime {symbol}: ошибка get_klines(60): {exc}")
        raw_1h = []
    atr_1h_now = 0.0
    if raw_1h:
        try:
            highs = [float(k[2]) for k in raw_1h]
            lows = [float(k[3]) for k in raw_1h]
            closes = [float(k[4]) for k in raw_1h]
            atr_series = strategy_v2.atr(highs, lows, closes, 14)
            if atr_series and atr_series[-1] is not None:
                atr_1h_now = float(atr_series[-1])
        except Exception as exc:  # noqa: BLE001
            print(f"[AI] regime {symbol}: ошибка расчёта ATR(1h): {exc}")

    # Реализованная волатильность 30d.
    realized_vol_30d = 0.0
    closes_d = [row["close"] for row in daily_ohlc]
    if len(closes_d) >= 31:
        returns: list[float] = []
        for i in range(len(closes_d) - 30, len(closes_d)):
            prev = closes_d[i - 1]
            cur = closes_d[i]
            if prev > 0:
                returns.append((cur - prev) / prev)
        if len(returns) >= 2:
            try:
                realized_vol_30d = statistics.stdev(returns) * math.sqrt(365.0)
            except statistics.StatisticsError:
                realized_vol_30d = 0.0

    # Заголовки (до 10 штук).
    try:
        headlines = await news_engine.fetch_headlines(session, page_size=10)
    except Exception as exc:  # noqa: BLE001
        print(f"[AI] regime {symbol}: ошибка fetch_headlines: {exc}")
        headlines = []

    try:
        result = await ai_regime.classify(
            session, symbol, daily_ohlc, atr_1h_now, realized_vol_30d, headlines
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[AI] regime {symbol}: ошибка classify: {exc}")
        return

    if isinstance(result, dict) and result.get("regime"):
        sym_state["regime"] = result
        sym_state["last_regime_check_epoch"] = time.time()
        print(
            f"[AI] regime {symbol}: {result.get('regime')} "
            f"conf={result.get('confidence')} reason={result.get('reason')}"
        )


async def _weekly_postmortem_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    now: datetime,
) -> None:
    if now.weekday() != int(config.POSTMORTEM_DAY_UTC):
        return
    if now.hour != int(config.POSTMORTEM_HOUR_UTC):
        return
    g = state["global"]
    cur_week = _iso_week_key(now)
    if g.get("last_postmortem_iso_week") == cur_week:
        return
    try:
        text = await ai_postmortem.report(session, days=7)
    except Exception as exc:  # noqa: BLE001
        print(f"[AI] postmortem: ошибка вызова: {exc}")
        return
    if not text:
        return
    body = text if len(text) <= 3800 else text[:3800].rstrip()
    try:
        await telegram_bot.send_message(
            session,
            "📈 <b>Еженедельный отчёт</b>\n\n" + body,
            reply_markup=telegram_bot.set_keyboard(),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[AI] postmortem: ошибка отправки в Telegram: {exc}")
    g["last_postmortem_iso_week"] = cur_week
    print(f"[AI] postmortem отправлен за неделю {cur_week}")


# --- Торговые помощники ---------------------------------------------------

def _bybit_kline_to_dict(k: list[Any]) -> dict[str, Any]:
    return {
        "ts": int(k[0]),
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "volume": float(k[5]) if len(k) > 5 else 0.0,
    }


def _sum_open_risk(state: dict[str, Any]) -> float:
    equity_start = float(state["global"].get("equity_start") or 0.0)
    if equity_start <= 0:
        return 0.0
    total = 0.0
    for sym_state in state["symbols"].values():
        trade = sym_state.get("open_trade")
        if not trade:
            continue
        entry = float(trade.get("entry_price") or 0.0)
        stop = float(trade.get("current_stop") or 0.0)
        qty = float(trade.get("qty") or 0.0)
        if entry <= 0 or qty <= 0:
            continue
        total += abs(entry - stop) * qty / equity_start
    return total


async def _manage_open_trade(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    symbol: str,
    candles_1h: list[dict[str, Any]],
    now: datetime,
) -> None:
    sym_state = state["symbols"][symbol]
    trade = sym_state.get("open_trade")
    if not trade or not candles_1h:
        return

    last_bar = candles_1h[-1]
    last_high = float(last_bar.get("high") or 0.0)
    last_low = float(last_bar.get("low") or 0.0)
    last_close = float(last_bar.get("close") or 0.0)

    high_since = max(float(trade.get("high_since_entry") or trade["entry_price"]), last_high)
    low_since = min(float(trade.get("low_since_entry") or trade["entry_price"]), last_low)
    trade["high_since_entry"] = high_since
    trade["low_since_entry"] = low_since

    side = str(trade.get("side") or "")
    side_str = "long" if side == "Buy" else "short"
    entry = float(trade.get("entry_price") or 0.0)
    atr_at_entry = float(trade.get("atr_at_entry") or 0.0)
    current_stop = float(trade.get("current_stop") or 0.0)

    # ATR «сейчас» - последний ATR по часовому ряду.
    try:
        highs = [c["high"] for c in candles_1h]
        lows = [c["low"] for c in candles_1h]
        closes = [c["close"] for c in candles_1h]
        atr_series = strategy_v2.atr(highs, lows, closes, 14)
        atr_now = float(atr_series[-1]) if atr_series and atr_series[-1] is not None else atr_at_entry
    except Exception:  # noqa: BLE001
        atr_now = atr_at_entry

    try:
        new_trail = strategy_v2.compute_chandelier(
            high_since,
            low_since,
            atr_now,
            side_str,
            entry,
            activation_atr=atr_at_entry,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[LOOP] {symbol}: ошибка compute_chandelier: {exc}")
        new_trail = None

    if new_trail is not None:
        tighter = False
        if side == "Buy" and new_trail > current_stop:
            tighter = True
        elif side == "Sell" and (current_stop == 0 or new_trail < current_stop):
            tighter = True
        if tighter:
            try:
                resp = await EXCHANGE.set_trading_stop(
                    session, symbol, stop_loss=float(new_trail)
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[LOOP] {symbol}: ошибка set_trading_stop: {exc}")
                resp = None
            if resp and resp.get("retCode") == 0:
                trade["current_stop"] = float(new_trail)
                print(f"[LOOP] {symbol}: трейлинг подтянут -> {new_trail}")

    # Таймстоп.
    try:
        time_stop = strategy_v2.should_time_stop(
            trade.get("entry_ts_iso") or "",
            _iso(now),
            side_str,
            entry,
            last_close,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[LOOP] {symbol}: ошибка should_time_stop: {exc}")
        time_stop = False
    if time_stop:
        close_side = "Sell" if side == "Buy" else "Buy"
        qty = float(trade.get("qty") or 0.0)
        try:
            resp = await EXCHANGE.place_order_with_fallback(
                session,
                symbol=symbol,
                side=close_side,
                qty=qty,
                reduce_only=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[LOOP] {symbol}: ошибка закрытия по таймстопу: {exc}")
            resp = None
        if resp and resp.get("retCode") == 0:
            print(f"[LOOP] {symbol}: закрытие по таймстопу ({config.TIME_STOP_HOURS}ч)")


async def _check_closed_exchange_position(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    symbol: str,
) -> None:
    sym_state = state["symbols"][symbol]
    trade = sym_state.get("open_trade")
    if not trade:
        return
    try:
        positions = await EXCHANGE.get_positions(session, symbol)
    except Exception as exc:  # noqa: BLE001
        print(f"[LOOP] {symbol}: ошибка get_positions: {exc}")
        return
    if positions:
        return  # позиция всё ещё открыта

    # --- Пытаемся получить реальный PnL через closed-pnl адаптера ---
    real_pnl = None
    real_exit_price = None
    try:
        closed_records = await EXCHANGE.get_closed_pnl(session, symbol, limit=5)
        if closed_records:
            # Берём первую запись (самая свежая) как наиболее вероятное закрытие нашей позиции.
            rec = closed_records[0]
            real_pnl = float(rec.get("closedPnl") or 0)
            real_exit_price = float(rec.get("avgExitPrice") or 0)
            if real_exit_price > 0:
                print(f"[LOOP] Реальный exit price из closed-pnl: {real_exit_price}, PnL: {real_pnl}")
    except Exception as exc:  # noqa: BLE001
        print(f"[LOOP] Не удалось получить closed-pnl: {exc}")

    if real_pnl is not None and real_exit_price and real_exit_price > 0:
        exit_price = real_exit_price
        pnl = real_pnl
    else:
        # Fallback: аппроксимация через последнюю 1m свечу (менее точно).
        print("[LOOP] Используем аппроксимацию exit price через 1m kline")
        try:
            klines = await EXCHANGE.get_klines(session, symbol, "1", 1)
        except Exception as exc:  # noqa: BLE001
            print(f"[LOOP] {symbol}: ошибка получения 1m-свечи для выхода: {exc}")
            klines = []
        exit_price_fallback: Optional[float] = None
        if klines:
            try:
                exit_price_fallback = float(klines[-1][4])
            except (IndexError, TypeError, ValueError):
                exit_price_fallback = None
        if exit_price_fallback is None:
            exit_price_fallback = float(trade.get("current_stop") or trade.get("entry_price") or 0.0)

        exit_price = exit_price_fallback
        entry = float(trade.get("entry_price") or 0.0)
        qty = float(trade.get("qty") or 0.0)
        side = str(trade.get("side") or "")
        if side == "Buy":
            pnl = (exit_price - entry) * qty
        elif side == "Sell":
            pnl = (entry - exit_price) * qty
        else:
            pnl = 0.0
    outcome = "WIN" if pnl > 0 else "LOSS"

    trade_id = trade.get("id")
    if trade_id:
        try:
            memory.update_trade_outcome(int(trade_id), exit_price, pnl, outcome)
        except Exception as exc:  # noqa: BLE001
            print(f"[LOOP] {symbol}: ошибка update_trade_outcome: {exc}")

    g = state["global"]
    g["daily_pnl"] = float(g.get("daily_pnl", 0.0) or 0.0) + pnl
    g["weekly_pnl"] = float(g.get("weekly_pnl", 0.0) or 0.0) + pnl
    g["cumulative_pnl"] = float(g.get("cumulative_pnl", 0.0) or 0.0) + pnl
    equity_start = float(g.get("equity_start") or 0.0)
    proxy_equity = equity_start + float(g.get("cumulative_pnl", 0.0) or 0.0)
    _record_equity_snapshot(state, proxy_equity)

    print(
        f"[LOOP] {symbol}: позиция закрыта снаружи pnl={pnl:.4f} outcome={outcome} "
        f"daily={g['daily_pnl']:.4f} weekly={g['weekly_pnl']:.4f}"
    )

    # Push-уведомление о закрытии. Используем данные trade ДО того как
    # обнулим sym_state["open_trade"].
    try:
        entry = float(trade.get("entry_price") or 0.0)
        qty = float(trade.get("qty") or 0.0)
        side = str(trade.get("side") or "")
        side_label = "LONG" if side == "Buy" else "SHORT"
        pnl_pct = ((pnl / (entry * qty)) * 100) if entry > 0 and qty > 0 else 0.0
        outcome_emoji = "✅" if outcome == "WIN" else "❌"
        duration = _format_duration(trade.get("entry_ts_iso"), _utc_now())
        notify_text = (
            f"{outcome_emoji} <b>Закрыта {symbol} {side_label}</b>\n"
            f"Вход: {entry:.4f} → Выход: {exit_price:.4f}\n"
            f"PnL: {pnl:+.4f} USDT ({pnl_pct:+.2f}%)\n"
            f"Исход: {outcome}\n"
            f"Длительность: {duration}\n"
            f"Суточный PnL: {g['daily_pnl']:+.4f} USDT"
        )
        await telegram_bot.send_message(
            session, notify_text, reply_markup=telegram_bot.set_keyboard()
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[LOOP] {symbol}: ошибка push-уведомления о закрытии: {exc}")

    sym_state["open_trade"] = None


# --- Основная логика по символу -----------------------------------------

async def _process_symbol(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    symbol: str,
    now: datetime,
) -> None:
    sym_state = state["symbols"][symbol]

    try:
        raw_1h = await EXCHANGE.get_klines(session, symbol, interval="60", limit=250)
        raw_4h = await EXCHANGE.get_klines(session, symbol, interval="240", limit=120)
        raw_1d = await EXCHANGE.get_klines(session, symbol, interval="D", limit=250)
    except Exception as exc:  # noqa: BLE001
        print(f"[LOOP] {symbol}: ошибка получения свечей: {exc}")
        return

    if not raw_1h or not raw_4h or not raw_1d:
        return  # транзиентная ошибка

    closed_1h = raw_1h[:-1]
    closed_4h = raw_4h[:-1]
    closed_1d = raw_1d[:-1]
    if len(closed_1h) < 21 or len(closed_4h) < 50 or len(closed_1d) < 200:
        return

    try:
        candles_1h = [_bybit_kline_to_dict(k) for k in closed_1h]
        candles_4h = [_bybit_kline_to_dict(k) for k in closed_4h]
        candles_1d = [_bybit_kline_to_dict(k) for k in closed_1d]
    except Exception as exc:  # noqa: BLE001
        print(f"[LOOP] {symbol}: ошибка парсинга свечей: {exc}")
        return

    last_bar_ts = candles_1h[-1]["ts"]

    # Сопровождение и детект внешнего закрытия.
    if sym_state.get("open_trade"):
        await _manage_open_trade(session, state, symbol, candles_1h, now)
    await _check_closed_exchange_position(session, state, symbol)

    if not state["global"].get("bot_running"):
        return
    if state["global"].get("kill_switch_state", "NONE") != "NONE":
        return
    if sym_state.get("open_trade"):
        return
    if sym_state.get("last_signal_bar_ts") == last_bar_ts:
        return
    # Продвигаем безусловно, чтобы не оценивать один бар повторно
    sym_state["last_signal_bar_ts"] = last_bar_ts

    try:
        closes = [c["close"] for c in candles_1h]
        highs = [c["high"] for c in candles_1h]
        lows = [c["low"] for c in candles_1h]
        atr_series = strategy_v2.atr(highs, lows, closes, 14)
        atr_1h_now = float(atr_series[-1]) if atr_series and atr_series[-1] is not None else 0.0
    except Exception as exc:  # noqa: BLE001
        print(f"[LOOP] {symbol}: ошибка расчёта ATR(1h): {exc}")
        atr_1h_now = 0.0

    ctx = {
        "symbol": symbol,
        "candles_1h": candles_1h,
        "candles_4h": candles_4h,
        "candles_1d": candles_1d,
        "equity": state["global"].get("equity_start") or 0.0,
        "atr_1h_now": atr_1h_now,
        "blackout": bool(state["global"].get("blackout", {}).get("blackout")),
        "regime": (sym_state.get("regime") or {}).get("regime", "TRENDING"),
    }

    order = strategy_v2.on_bar(ctx)
    if order is None:
        # Детерминированное отклонение - запомним последний фильтр.
        try:
            signal = strategy_v2.evaluate_signal(ctx)
        except Exception as exc:  # noqa: BLE001
            print(f"[LOOP] {symbol}: ошибка evaluate_signal: {exc}")
            return
        if signal.get("filter"):
            filter_tag = str(signal["filter"])
            detail = str(signal.get("reason", ""))
            indicators = signal.get("indicators") or {}
            rejection = {
                "ts": _iso(now),
                "symbol": symbol,
                "filter": filter_tag,
                "detail": detail,
                "indicators": indicators,
            }
            state["global"]["rejection_ring"].append(rejection)
            try:
                memory.record_rejected_check(symbol, filter_tag, detail, indicators)
            except Exception as exc:  # noqa: BLE001
                print(f"[LOOP] {symbol}: ошибка record_rejected_check: {exc}")
        return

    # Глобальный риск-кап.
    equity_start = float(state["global"].get("equity_start") or 0.0)
    added_risk = (
        abs(float(order["limit_price"]) - float(order["hard_stop"]))
        * float(order["qty"])
        / max(equity_start, 1.0)
    )
    open_risk = _sum_open_risk(state)
    if open_risk + added_risk > float(config.GLOBAL_RISK_CAP):
        print(
            f"[LOOP] {symbol}: нарушение глобального риск-лимита "
            f"({(open_risk + added_risk) * 100:.2f}% > "
            f"{config.GLOBAL_RISK_CAP * 100:.2f}%), пропуск"
        )
        return

    # Биржевые фильтры.
    try:
        info = await EXCHANGE.get_instrument_info(session, symbol)
    except Exception as exc:  # noqa: BLE001
        print(f"[LOOP] {symbol}: ошибка instrument_info_cached: {exc}")
        return
    if info is None:
        print(f"[LOOP] {symbol}: нет данных инструмента, пропуск")
        return

    qty = EXCHANGE.validate_and_round_qty(
        float(order["qty"]), info, float(order["limit_price"])
    )
    if qty <= 0:
        print(f"[LOOP] {symbol}: qty не прошла фильтры ({order['qty']}) - пропуск")
        return

    side = str(order["side"])
    try:
        resp = await EXCHANGE.place_order_with_fallback(
            session,
            symbol=symbol,
            side=side,
            qty=qty,
            stop_loss=float(order["hard_stop"]),
            take_profit=None,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[LOOP] {symbol}: ошибка размещения ордера: {exc}")
        return
    if not resp or resp.get("retCode") != 0:
        print(f"[LOOP] {symbol}: ордер не прошёл ({resp})")
        return

    entry_price = float(resp.get("fill_price") or order.get("limit_price") or 0.0)
    try:
        trade_id = memory.record_trade(
            symbol=symbol,
            side=("LONG" if side == "Buy" else "SHORT"),
            entry=entry_price,
            qty=qty,
            atr_val=atr_1h_now,
            ai_reason=(order.get("meta") or {}).get("reason"),
            outcome="OPEN",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[LOOP] {symbol}: ошибка record_trade: {exc}")
        trade_id = None

    sym_state["open_trade"] = {
        "id": trade_id,
        "side": side,
        "entry_price": entry_price,
        "qty": qty,
        "atr_at_entry": atr_1h_now,
        "entry_ts_iso": _iso(now),
        "high_since_entry": entry_price,
        "low_since_entry": entry_price,
        "current_stop": float(order["hard_stop"]),
    }
    print(
        f"[LOOP] {symbol}: открыта {side} qty={qty} entry={entry_price} "
        f"stop={order['hard_stop']}"
    )

    # Push-уведомление в Telegram об открытии позиции.
    # Ошибку отправки логгируем, но цикл не валим - Telegram может быть
    # временно недоступен, торговля важнее уведомлений.
    try:
        hard_stop = float(order["hard_stop"])
        side_label = "LONG" if side == "Buy" else "SHORT"
        side_emoji = "🟢" if side == "Buy" else "🔴"
        notional = entry_price * qty
        stop_pct = (
            ((entry_price - hard_stop) / entry_price) * 100
            if side == "Buy" and entry_price > 0
            else ((hard_stop - entry_price) / entry_price) * 100
            if entry_price > 0
            else 0.0
        )
        reason = str((order.get("meta") or {}).get("reason") or "")
        notify_text = (
            f"{side_emoji} <b>Открыта {side_label} {symbol}</b>\n"
            f"Вход: {entry_price:.4f}\n"
            f"Размер: {qty} (~${notional:.2f})\n"
            f"Стоп: {hard_stop:.4f} (−{stop_pct:.2f}%)\n"
            f"Риск на сделку: {config.RISK_PER_TRADE * 100:.2f}%"
        )
        if reason:
            notify_text += f"\nПричина: {reason}"
        await telegram_bot.send_message(
            session, notify_text, reply_markup=telegram_bot.set_keyboard()
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[LOOP] {symbol}: ошибка push-уведомления об открытии: {exc}")


# --- Главный цикл ---------------------------------------------------------

async def trading_loop(
    state: dict[str, Any],
    session: aiohttp.ClientSession,
) -> None:
    print("[LOOP] Торговый цикл v2 запущен")
    while True:
        try:
            now = _utc_now()
            _roll_daily_weekly_anchors(state, now)
            _reset_kill_switches_if_due(state, now)
            await _hourly_macro_tick(session, state, now)

            for symbol in config.SYMBOLS:
                try:
                    await _regime_tick(session, state, symbol, now)
                    await _process_symbol(session, state, symbol, now)
                except Exception as exc:  # noqa: BLE001
                    print(f"[LOOP] {symbol}: ошибка тика: {exc}")

            await _apply_kill_switches(session, state, now)
            await _weekly_postmortem_tick(session, state, now)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[LOOP] Транзиентная ошибка тика: {exc}")

        await asyncio.sleep(TICK_SECONDS)


def _build_state() -> dict[str, Any]:
    return {
        "symbols": {
            symbol: {
                "open_trade": None,
                "last_signal_bar_ts": 0,
                "regime": {
                    "regime": "TRENDING",
                    "confidence": 0,
                    "reason": "",
                    "ts": None,
                    "symbol": symbol,
                },
                "last_regime_check_epoch": 0.0,
            }
            for symbol in config.SYMBOLS
        },
        "global": {
            "bot_running": True,
            "equity_start": None,
            "hwm": 0.0,
            "daily_pnl": 0.0,
            "daily_anchor_iso": None,
            "weekly_pnl": 0.0,
            "weekly_anchor_iso": None,
            "cumulative_pnl": 0.0,
            "kill_switch_state": "NONE",
            "kill_until_utc": None,
            "kill_detail": "",
            "blackout": {
                "blackout": False,
                "until_utc": None,
                "reason": "",
                "ts": None,
            },
            "last_macro_check_epoch": 0.0,
            "last_postmortem_iso_week": None,
            "rejection_ring": collections.deque(maxlen=50),
        },
        "instruments": {},
    }


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
    state = _build_state()

    async with aiohttp.ClientSession() as session:
        print("[MAIN] Zenith-Control Ultimate v2 запущен")

        # Стартовый баланс: ставим equity_start и HWM. На сбое биржи - warn.
        exch_label = config.EXCHANGE.upper()
        try:
            balance = await EXCHANGE.get_balance(session, "USDT")
        except Exception as exc:  # noqa: BLE001
            balance = None
            print(f"[MAIN] Ошибка при проверке авторизации {exch_label}: {exc}")

        if balance is None:
            print(
                f"[MAIN] Не удалось получить баланс {exch_label}. "
                "Цикл всё равно стартует, но входов не будет до ручной "
                "проверки ключей/сети."
            )
        else:
            mode = "TESTNET" if config.IS_TESTNET else "MAINNET"
            print(
                f"[MAIN] Успех авторизации на {exch_label} ({mode}). "
                f"Баланс USDT: {balance:.4f}"
            )
            state["global"]["equity_start"] = float(balance)
            state["global"]["hwm"] = float(balance)
            _record_equity_snapshot(state, float(balance))

        # Прогрев кэша инструментов.
        for symbol in config.SYMBOLS:
            try:
                info = await EXCHANGE.get_instrument_info(session, symbol)
            except Exception as exc:  # noqa: BLE001
                info = None
                print(f"[MAIN] instrument_info_cached({symbol}) сбой: {exc}")
            if info is not None:
                state["instruments"][symbol] = info

        print("[MAIN] Telegram-бот запущен в режиме Long Polling")
        await telegram_bot.send_message(
            session,
            (
                "🚀 <b>Zenith-Control Ultimate v2</b> запущен.\n"
                "Мульти-символ: " + ", ".join(config.SYMBOLS) + ".\n"
                "Выберите действие ниже."
            ),
            reply_markup=telegram_bot.set_keyboard(),
        )
        await asyncio.gather(
            trading_loop(state, session),
            telegram_bot.run_bot(state, session),
        )


if __name__ == "__main__":
    asyncio.run(main())
