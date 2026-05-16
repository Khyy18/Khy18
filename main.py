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
import signal
import statistics
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiohttp

import ai_macro_sentinel
import ai_postmortem
import ai_regime
import api_engine  # noqa: F401  # legacy shim, поддерживается для совместимости
import beta_estimator
import config
import memory
import news_engine
import strategy_v2
import telegram_bot
from exchanges import get_adapter
from logging_config import get_logger

log = get_logger(__name__)


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

    # Сохраняем дневные closes этого символа в state для пересчёта rolling-беты.
    # Беты пересчитываем отдельной функцией _maybe_recompute_betas раз в
    # сутки, не на каждом regime_tick. Здесь только обновляем "сырьё".
    sym_state["last_daily_closes"] = closes_d


async def _maybe_recompute_betas(state: dict[str, Any]) -> None:
    """Раз в сутки пересчитываем rolling-беты по последним дневным закрытиям.

    Берём state["symbols"][sym]["last_daily_closes"] - там лежит то, что
    последний _regime_tick загрузил из биржи (срок жизни AI_REGIME_TTL_SEC,
    т.е. 1 час). Если у какого-то символа их ещё нет (regime_tick не
    запускался) - используем дефолтные беты для этого символа.
    """
    if not beta_estimator.is_stale():
        return
    daily_closes_by_symbol: dict[str, list[float]] = {}
    for sym, sym_st in state["symbols"].items():
        closes = sym_st.get("last_daily_closes") or []
        if closes and len(closes) >= beta_estimator.MIN_BARS_FOR_BETA:
            daily_closes_by_symbol[sym] = [float(c) for c in closes]
    if not daily_closes_by_symbol or "BTCUSDT" not in daily_closes_by_symbol:
        # Без BTC как референса считать нечего. Подождём следующего regime_tick.
        return
    try:
        betas = beta_estimator.compute_betas(daily_closes_by_symbol)
        beta_estimator.save_cached(betas)
        print(
            "[BETA] Пересчёт rolling-беты: "
            + ", ".join(f"{s}={v:.2f}" for s, v in betas.items())
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[BETA] Ошибка пересчёта: {exc}")


# --- Reconcile / Net beta / Daily PnL push / Graceful degradation --------

async def _reconcile_open_positions(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
) -> None:
    """Синхронизировать локальный state с реальными открытыми позициями биржи.

    Сценарий: бот перезапустили (рестарт VPS, обновление контейнера), но на
    бирже остались открытые позиции из прошлой сессии. Без reconcile цикл
    решит, что позиций нет, попробует открыть новые - и нарушит риск-лимит,
    либо оставит чужую позицию без управления (трейл/таймстоп).

    Что делаем:
      - для каждого символа спрашиваем биржу про позицию;
      - если есть, заполняем sym_state["open_trade"] из биржевых полей,
        чтобы _manage_open_trade подхватил трейлинг.
      - PnL не восстанавливаем (нет источника правды для сегодняшнего якоря),
        просто стартуем с чистого daily_pnl. Закрытие позиции после рестарта
        потом начислит PnL через _check_closed_exchange_position.

    Если биржа не отвечает - молча идём дальше, цикл и так запустится.
    """
    print("[RECONCILE] Сверка локального state с открытыми позициями биржи...")
    restored = 0
    for symbol in config.SYMBOLS:
        try:
            positions = await EXCHANGE.get_positions(session, symbol)
        except Exception as exc:  # noqa: BLE001
            print(f"[RECONCILE] {symbol}: ошибка get_positions: {exc}")
            continue
        if not positions:
            continue

        pos = positions[0] if isinstance(positions, list) else positions
        try:
            size = float(pos.get("size") or pos.get("qty") or 0.0)
            entry = float(pos.get("avgPrice") or pos.get("entry_price") or 0.0)
            side_raw = str(pos.get("side") or "")
            stop_raw = pos.get("stopLoss") or pos.get("stop_loss") or 0.0
            stop = float(stop_raw or 0.0)
        except (TypeError, ValueError) as exc:
            print(f"[RECONCILE] {symbol}: парс позиции: {exc}")
            continue
        if size <= 0 or entry <= 0:
            continue

        # Унифицируем сторону: Bybit -> 'Buy'/'Sell', OKX -> 'long'/'short'.
        if side_raw.lower() in ("long", "buy"):
            side = "Buy"
        elif side_raw.lower() in ("short", "sell"):
            side = "Sell"
        else:
            print(f"[RECONCILE] {symbol}: неизвестная сторона {side_raw!r}, пропуск")
            continue

        sym_state = state["symbols"][symbol]
        if sym_state.get("open_trade"):
            continue  # уже знаем (вряд ли при свежем старте, но на всякий)

        sym_state["open_trade"] = {
            "id": None,  # биржевая позиция не привязана к нашему trade_id в memory
            "side": side,
            "entry_price": entry,
            "qty": size,
            # ATR на момент входа неизвестен - подменяем 0 и пересчитаем при
            # первом тике из ATR по 1h-свечам в _manage_open_trade.
            "atr_at_entry": 0.0,
            "entry_ts_iso": _iso(_utc_now()),
            "high_since_entry": entry,
            "low_since_entry": entry,
            "current_stop": stop or entry,
            "reconciled": True,
        }
        # Создаём запись в memory с outcome='OPEN', чтобы при последующем
        # закрытии _check_closed_exchange_position смог обновить её через
        # update_trade_outcome. Без этого reconciled-сделка не попадает в
        # итоговую статистику — get_stats игнорирует OPEN.
        try:
            trade_id = memory.record_trade(
                symbol=symbol,
                side=("LONG" if side == "Buy" else "SHORT"),
                entry=entry,
                qty=size,
                atr_val=0.0,
                ai_reason="reconciled-after-restart",
                outcome="OPEN",
            )
            sym_state["open_trade"]["id"] = trade_id
        except Exception as exc:  # noqa: BLE001
            print(f"[RECONCILE] {symbol}: не удалось записать в memory: {exc}")
        restored += 1
        print(
            f"[RECONCILE] {symbol}: восстановлена позиция side={side} "
            f"qty={size} entry={entry} stop={stop}"
        )

    if restored == 0:
        print("[RECONCILE] Открытых позиций на бирже не найдено")
    else:
        print(f"[RECONCILE] Восстановлено позиций: {restored}")


# Веса волатильности (бета относительно BTC) - используются как
# приближённое "сколько долларов риска эквивалентно одному доллару BTC".
# Это всего лишь дефолты и fallback на случай, когда rolling-беты ещё
# не насчитаны (первый запуск или нет дневных данных). Реальные
# актуальные значения тянутся из beta_estimator.load_cached() при
# каждой проверке correlation guard - они пересчитываются раз в сутки
# в _regime_tick после получения дневных свечей по всем символам.
_BETA_TO_BTC: dict[str, float] = dict(beta_estimator.DEFAULT_BETAS)


def _get_betas() -> dict[str, float]:
    """Текущие беты для correlation guard.

    Сначала пробуем тёплый кэш в memory.kv_store; если он пустой или
    проигрался импорт - возвращаем _BETA_TO_BTC. Этот хелпер вызывается
    в hot-path _process_symbol на каждом сигнале - там всё локально.
    """
    try:
        return beta_estimator.load_cached()
    except Exception:  # noqa: BLE001
        return dict(_BETA_TO_BTC)


def _net_beta_exposure(state: dict[str, Any]) -> float:
    """Суммарный направленный риск портфеля в "BTC-единицах".

    Каждой открытой позиции присваиваем знак (long=+1, short=-1) и вес
    beta_to_btc[symbol]. Сумма (signed_qty * entry_price * beta) / equity
    даёт направленный leverage. CAP = 2.0 означает: суммарная "длинная
    BTC-эквивалентная" экспозиция не должна превышать 2x equity. Это
    защищает от наивного "купим 3 коррелированных альта на 1% риска
    каждый" - в кризис они все падают разом и съедят 9% equity.

    Для шортов знак минус, поэтому LONG BTC + SHORT ETH частично
    компенсируют друг друга и не блокируются.
    """
    equity_start = float(state["global"].get("equity_start") or 0.0)
    if equity_start <= 0:
        return 0.0
    betas = _get_betas()
    total = 0.0
    for symbol, sym_state in state["symbols"].items():
        trade = sym_state.get("open_trade")
        if not trade:
            continue
        side = str(trade.get("side") or "")
        qty = float(trade.get("qty") or 0.0)
        entry = float(trade.get("entry_price") or 0.0)
        beta = float(betas.get(symbol, 1.0))
        sign = 1.0 if side == "Buy" else -1.0 if side == "Sell" else 0.0
        if qty <= 0 or entry <= 0 or sign == 0.0:
            continue
        total += sign * qty * entry * beta
    return abs(total) / equity_start


async def _daily_pnl_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    now: datetime,
) -> None:
    """Раз в сутки в 00:00 UTC шлём в Telegram сводку PnL за прошедший день.

    Идемпотентность: сохраняем дату последнего пуша в global.last_daily_push_date.
    Внутри _roll_daily_weekly_anchors суточный якорь обнуляется в начале новых
    суток, поэтому daily_pnl читаем ДО обнуления. Это значит daily_pnl_tick
    должен запускаться ДО _roll_daily_weekly_anchors на новом дне.

    Алгоритм:
      - если час != 0 - пропуск;
      - если последняя дата отправки == сегодняшняя дата (UTC) - пропуск;
      - иначе формируем отчёт и шлём.
    """
    if now.hour != 0:
        return

    g = state["global"]
    today_str = now.strftime("%Y-%m-%d")
    last_pushed = g.get("last_daily_push_date")
    if last_pushed == today_str:
        return

    daily_pnl = float(g.get("daily_pnl", 0.0) or 0.0)
    weekly_pnl = float(g.get("weekly_pnl", 0.0) or 0.0)
    cumulative_pnl = float(g.get("cumulative_pnl", 0.0) or 0.0)
    equity_start = float(g.get("equity_start") or 0.0)
    proxy_equity = equity_start + cumulative_pnl

    # Сделок за сутки - по записям в memory (если доступно).
    trades_today = 0
    wins = 0
    try:
        recent = memory.get_trades_since(2) or []
        target_date = (now - timedelta(days=1)).date()
        for tr in recent:
            ts_str = tr.get("entry_time") or tr.get("ts") or ""
            if not ts_str:
                continue
            ts = _from_iso(str(ts_str))
            if ts is None:
                continue
            if ts.date() == target_date:
                trades_today += 1
                if (tr.get("outcome") or "").upper() == "WIN":
                    wins += 1
    except Exception as exc:  # noqa: BLE001
        print(f"[DAILY] Не удалось посчитать сделки за сутки: {exc}")

    arrow = "▲" if daily_pnl > 0 else "▼" if daily_pnl < 0 else "•"
    pct = (daily_pnl / equity_start * 100) if equity_start > 0 else 0.0
    if trades_today > 0:
        winrate = (wins / trades_today * 100) if trades_today else 0.0
        trades_line = f"Сделок за день: {trades_today} (winrate {winrate:.0f}%)"
    else:
        # Не показываем "0% winrate" - это шум. Может ввести в заблуждение
        # ("стратегия проигрывает 100% времени"), хотя сделок просто не было.
        trades_line = "Сделок за день: нет"
    text = (
        "🌅 <b>Итоги дня</b>\n"
        f"Дата (UTC): {(now - timedelta(days=1)).strftime('%Y-%m-%d')}\n"
        f"Суточный PnL: {arrow} {daily_pnl:+.4f} USDT ({pct:+.2f}%)\n"
        f"Недельный PnL: {weekly_pnl:+.4f} USDT\n"
        f"Кумулятивный PnL: {cumulative_pnl:+.4f} USDT\n"
        f"Эквити (proxy): {proxy_equity:.2f} USDT\n"
        f"{trades_line}"
    )

    try:
        await telegram_bot.send_message(
            session, text, reply_markup=telegram_bot.set_keyboard()
        )
        print(f"[DAILY] Сводка за {today_str} отправлена в Telegram")
    except Exception as exc:  # noqa: BLE001
        print(f"[DAILY] Ошибка отправки сводки: {exc}")

    g["last_daily_push_date"] = today_str


async def _try_recover_from_degradation(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
) -> None:
    """Если бот в graceful-degradation, периодически пробуем health-check.

    Логика: раз в `RECOVERY_PROBE_INTERVAL_SEC` дёргаем
    EXCHANGE.get_server_time как самый дешёвый авторизованный вызов. Если
    он вернул не-None - биржа отвечает, восстанавливаем bot_running=True
    и сбрасываем degraded. Если по-прежнему не отвечает - оставляем в
    паузе.

    Без этой функции пользователю надо вручную нажимать ▶️ после каждого
    транзиентного сбоя (в облаке такие сбои случаются регулярно).
    """
    g = state["global"]
    if not g.get("degraded"):
        return
    interval = float(
        getattr(config, "RECOVERY_PROBE_INTERVAL_SEC", 5 * 60)
    )
    last_epoch = float(g.get("last_recovery_probe_epoch") or 0.0)
    if (time.time() - last_epoch) < interval:
        return
    g["last_recovery_probe_epoch"] = time.time()

    try:
        server_time = await EXCHANGE.get_server_time(session)
    except Exception as exc:  # noqa: BLE001
        print(f"[RECOVERY] probe не прошёл: {exc}")
        return
    if server_time is None:
        # Биржа всё ещё не отвечает - остаёмся в паузе.
        return

    # Биржа жива - снимаем паузу.
    print("[RECOVERY] Биржа отвечает, снимаем degraded и возобновляем торговлю")
    g["bot_running"] = True
    g["degraded"] = False
    last_reason = str(g.get("degraded_reason") or "")
    g["degraded_reason"] = ""
    try:
        await telegram_bot.send_message(
            session,
            (
                "✅ <b>Auto-recovery</b>\n"
                "Биржа снова отвечает, торговля возобновлена автоматически.\n"
                f"Причина паузы: <code>{last_reason[:200]}</code>"
            ),
            reply_markup=telegram_bot.set_keyboard(),
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[RECOVERY] не удалось отправить уведомление: {exc}")


async def _heartbeat_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    now: datetime,
) -> None:
    """Раз в HEARTBEAT_INTERVAL_SEC шлём в Telegram короткую сводку "я жив".

    Первый heartbeat отправляем отложенно: пропускаем самый первый тик
    (чтобы не пришло сразу после стартового сообщения), второй тик через
    HEARTBEAT_INTERVAL_SEC уже уйдёт. Это даёт пользователю контрольную
    точку: если сообщение не пришло в срок - бот лёг.
    """
    g = state["global"]
    last_epoch = float(g.get("last_heartbeat_epoch") or 0.0)
    interval = float(getattr(config, "HEARTBEAT_INTERVAL_SEC", 6 * 3600))

    # Первый вызов: не шлём, просто ставим якорь, чтобы следующий
    # heartbeat улетел через полный интервал после старта процесса.
    if last_epoch <= 0:
        g["last_heartbeat_epoch"] = time.time()
        return

    if (time.time() - last_epoch) < interval:
        return

    # Собираем короткую сводку.
    bot_running = "ON" if g.get("bot_running", True) else "OFF"
    ks = str(g.get("kill_switch_state") or "NONE")
    daily_pnl = float(g.get("daily_pnl", 0.0) or 0.0)
    weekly_pnl = float(g.get("weekly_pnl", 0.0) or 0.0)
    equity_start = g.get("equity_start")
    cumulative_pnl = float(g.get("cumulative_pnl", 0.0) or 0.0)
    proxy_equity = (
        float(equity_start) + cumulative_pnl if equity_start is not None else None
    )
    blackout = bool((g.get("blackout") or {}).get("blackout"))
    blackout_str = "ON" if blackout else "OFF"

    # Количество открытых позиций и отклонений за последние 6ч.
    open_positions = sum(
        1 for s in state["symbols"].values() if s.get("open_trade")
    )
    rejection_ring = g.get("rejection_ring") or []
    cutoff = now - timedelta(seconds=interval)
    recent_rejections = 0
    for r in rejection_ring:
        ts = _from_iso(r.get("ts"))
        if ts is not None and ts >= cutoff:
            recent_rejections += 1

    equity_line = (
        f"{proxy_equity:.2f}" if proxy_equity is not None else "-"
    )
    parts = [
        "💓 <b>Heartbeat</b> - бот жив",
        f"Время: {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Торговля: {bot_running}  |  Kill-switch: {ks}  |  Blackout: {blackout_str}",
        f"Эквити: {equity_line} USDT (cum PnL {cumulative_pnl:+.2f})",
        f"PnL суточный: {daily_pnl:+.4f}  |  недельный: {weekly_pnl:+.4f}",
        f"Открытых позиций: {open_positions} / {len(config.SYMBOLS)}",
        f"Отклонений за {int(interval / 3600)}ч: {recent_rejections}",
    ]

    try:
        await telegram_bot.send_message(
            session,
            "\n".join(parts),
            reply_markup=telegram_bot.set_keyboard(),
        )
        print("[HB] Heartbeat отправлен в Telegram")
    except Exception as exc:  # noqa: BLE001
        print(f"[HB] Ошибка отправки heartbeat: {exc}")

    g["last_heartbeat_epoch"] = time.time()


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
            if getattr(config, "DRY_RUN", False):
                print(f"[DRY RUN] {symbol}: would tighten trail stop -> {new_trail}")
                trade["current_stop"] = float(new_trail)
                return
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
        if getattr(config, "DRY_RUN", False):
            print(
                f"[DRY RUN] {symbol}: would close by time-stop "
                f"({config.TIME_STOP_HOURS}ч), side={close_side} qty={qty}"
            )
            return
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

    # Correlation guard: считаем суммарную направленную BTC-эквивалентную
    # экспозицию С УЧЁТОМ предполагаемой новой позиции. Это ловит сценарий
    # "три одинаково настроенные long на BTC/ETH/SOL по 1% риска" - они
    # коррелированы, в кризис идут в одну сторону и фактический риск >> 3%.
    beta_cap = float(getattr(config, "NET_BETA_CAP", 2.0))
    betas = _get_betas()
    side_sign = 1.0 if str(order["side"]) == "Buy" else -1.0
    proposed_beta = float(betas.get(symbol, 1.0))
    proposed_notional = (
        float(order["limit_price"]) * float(order["qty"]) * proposed_beta * side_sign
    )
    # Текущая чистая (со знаком) экспозиция:
    current_signed = 0.0
    for s, sym_st in state["symbols"].items():
        tr = sym_st.get("open_trade")
        if not tr:
            continue
        sd = str(tr.get("side") or "")
        qty_t = float(tr.get("qty") or 0.0)
        ent = float(tr.get("entry_price") or 0.0)
        b = float(betas.get(s, 1.0))
        sg = 1.0 if sd == "Buy" else -1.0 if sd == "Sell" else 0.0
        if qty_t > 0 and ent > 0 and sg != 0.0:
            current_signed += sg * qty_t * ent * b
    new_net_exposure = abs(current_signed + proposed_notional) / max(equity_start, 1.0)
    if new_net_exposure > beta_cap:
        print(
            f"[LOOP] {symbol}: net beta cap превышен "
            f"({new_net_exposure:.2f}x > {beta_cap:.2f}x), пропуск"
        )
        try:
            memory.record_rejected_check(
                symbol,
                "net_beta_cap",
                f"net_exposure={new_net_exposure:.2f}x > cap={beta_cap:.2f}x",
                {"net_exposure": new_net_exposure, "cap": beta_cap},
            )
        except Exception:
            pass
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
    if getattr(config, "DRY_RUN", False):
        side_label = "LONG" if side == "Buy" else "SHORT"
        print(
            f"[DRY RUN] {symbol}: would open {side_label} qty={qty} "
            f"limit={order.get('limit_price')} stop={order.get('hard_stop')}"
        )
        return
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
    consecutive_errors = 0
    error_threshold = int(getattr(config, "GRACEFUL_DEGRADATION_THRESHOLD", 5))
    while True:
        try:
            now = _utc_now()
            # Daily push идёт ДО ротации якорей: после ротации daily_pnl=0
            # и сводка станет бессмысленной.
            await _daily_pnl_tick(session, state, now)
            _roll_daily_weekly_anchors(state, now)
            _reset_kill_switches_if_due(state, now)
            await _hourly_macro_tick(session, state, now)

            for symbol in config.SYMBOLS:
                try:
                    await _regime_tick(session, state, symbol, now)
                    await _process_symbol(session, state, symbol, now)
                except Exception as exc:  # noqa: BLE001
                    print(f"[LOOP] {symbol}: ошибка тика: {exc}")

            await _maybe_recompute_betas(state)
            await _apply_kill_switches(session, state, now)
            await _try_recover_from_degradation(session, state)
            await _heartbeat_tick(session, state, now)
            await _weekly_postmortem_tick(session, state, now)

            # Тик прошёл без верхнеуровневой ошибки - сбрасываем счётчик.
            if consecutive_errors > 0:
                print(f"[LOOP] Восстановление после {consecutive_errors} ошибок")
                consecutive_errors = 0
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            consecutive_errors += 1
            print(
                f"[LOOP] Транзиентная ошибка тика "
                f"({consecutive_errors}/{error_threshold}): {exc}"
            )
            # Graceful degradation: после N подряд верхнеуровневых ошибок
            # ставим бот на паузу, чтобы не наплодить мусора в memory и
            # не отправить ордер по неполным данным. Снять можно из Telegram.
            if (
                consecutive_errors >= error_threshold
                and state["global"].get("bot_running", True)
            ):
                state["global"]["bot_running"] = False
                state["global"]["degraded"] = True
                state["global"]["degraded_reason"] = str(exc)[:200]
                print(
                    f"[LOOP] GRACEFUL DEGRADATION: {consecutive_errors} ошибок подряд, "
                    "торговля поставлена на паузу"
                )
                try:
                    await telegram_bot.send_message(
                        session,
                        (
                            "⚠️ <b>Graceful degradation</b>\n"
                            f"{consecutive_errors} ошибок подряд в trading_loop, "
                            "торговля поставлена на паузу.\n"
                            f"Последняя ошибка: <code>{str(exc)[:200]}</code>\n\n"
                            "Сопровождение открытых позиций продолжается. "
                            "Снять паузу - кнопка ▶️ в меню."
                        ),
                        reply_markup=telegram_bot.set_keyboard(),
                    )
                except Exception as nexc:  # noqa: BLE001
                    print(f"[LOOP] Не удалось отправить алерт degradation: {nexc}")

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
            "last_heartbeat_epoch": 0.0,
            "last_daily_push_date": None,
            "degraded": False,
            "degraded_reason": "",
            "last_recovery_probe_epoch": 0.0,
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

    # Graceful shutdown: asyncio.Event + signal handlers.
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        log.info("shutdown_signal_received")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

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

        # Reconcile: подхватить открытые позиции, оставшиеся с прошлой
        # сессии (рестарт VPS, обновление контейнера). Если biржа лежит -
        # просто стартуем без восстановления, ничего критичного.
        try:
            await _reconcile_open_positions(session, state)
        except Exception as exc:  # noqa: BLE001
            print(f"[MAIN] Ошибка reconcile (не критично): {exc}")

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

        # Background tasks including shutdown waiter.
        tasks = [
            asyncio.create_task(trading_loop(state, session), name="trading_loop"),
            asyncio.create_task(telegram_bot.run_bot(state, session), name="telegram_bot"),
            asyncio.create_task(shutdown_event.wait(), name="shutdown_waiter"),
        ]

        try:
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            # If shutdown_event fired, cancel remaining tasks.
            if shutdown_event.is_set():
                log.info("graceful_shutdown_started", pending=len(pending))
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
        finally:
            log.info("shutdown_complete")
            print("[MAIN] Graceful shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
