"""Momentum-стратегия: trend-following с EMA cross и leverage 3x.

Логика:
  1. Получаем свечи (15m по умолчанию).
  2. Считаем EMA fast (9) и EMA slow (21).
  3. Сигнал LONG: fast пересекает slow снизу вверх.
  4. Сигнал SHORT: fast пересекает slow сверху вниз.
  5. Входим с плечом MOMENTUM_LEVERAGE (default 3x).
  6. Выход: обратный crossover, стоп-лосс или тейк-профит.

Зарабатывает на трендовых движениях. Проигрывает в боковике.
Комбинация с grid (боковик) даёт диверсификацию.

Особенности:
  - Максимум MOMENTUM_MAX_POSITIONS одновременных позиций.
  - Стоп-лосс обязателен (MOMENTUM_STOP_LOSS_PCT).
  - НЕ торгует если global_kill_switch активен.
  - EMA считается на stdlib (без numpy/pandas).
"""

from __future__ import annotations

import time
from typing import Any, Optional

import aiohttp

import capital_allocator
import combo_config as cfg
import global_kill_switch
from exchanges import get_adapter
from utils.retry import retry_async
from exchanges.base import ExchangeAdapter
from regime_classifier import calc_adx


# ─── EMA расчёт (без numpy) ──────────────────────────────────────────

def calc_ema(prices: list[float], period: int) -> list[float]:
    """Exponential Moving Average. Возвращает список той же длины.

    Первые (period - 1) значений = SMA за доступные данные.
    """
    if not prices or period < 1:
        return []

    ema: list[float] = []
    multiplier = 2.0 / (period + 1)

    # Первое значение = SMA первых period точек (или сколько есть)
    initial_window = prices[:period]
    sma = sum(initial_window) / len(initial_window)
    ema.append(sma)

    for i in range(1, len(prices)):
        if i < period:
            # До набора полного окна — простое среднее
            window = prices[:i + 1]
            ema.append(sum(window) / len(window))
        else:
            prev = ema[-1]
            current = prices[i] * multiplier + prev * (1 - multiplier)
            ema.append(current)

    return ema


def calc_atr(klines: list[dict[str, Any]], period: int = 14) -> float:
    """Average True Range за последние period баров.

    TR = max(high - low, |high - prev_close|, |low - prev_close|)
    ATR = SMA(TR, period)

    Возвращает 0.0 при недостатке данных.
    """
    if len(klines) < period + 1:
        return 0.0

    trs: list[float] = []
    for i in range(1, len(klines)):
        high = float(klines[i]["high"])
        low = float(klines[i]["low"])
        prev_close = float(klines[i - 1]["close"])
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    # ATR = SMA последних period значений TR
    recent = trs[-period:]
    return sum(recent) / len(recent) if recent else 0.0


def calc_rsi(closes: list[float], period: int = 14) -> float:
    """Relative Strength Index (Wilder smoothing).

    Returns RSI value (0-100). Returns 50.0 if insufficient data.
    """
    if len(closes) < period + 1:
        return 50.0

    # Calculate price changes
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

    # Initial average gain/loss (SMA of first `period` changes)
    gains = [max(0, d) for d in deltas[:period]]
    losses = [max(0, -d) for d in deltas[:period]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    # Wilder smoothing for remaining
    for i in range(period, len(deltas)):
        change = deltas[i]
        gain = max(0, change)
        loss = max(0, -change)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def detect_crossover(
    fast_ema: list[float],
    slow_ema: list[float],
) -> Optional[str]:
    """Определить направление последнего пересечения EMA.

    Возвращает:
      "LONG"  — fast пересёк slow снизу вверх (бычий сигнал).
      "SHORT" — fast пересёк slow сверху вниз (медвежий сигнал).
      None    — пересечения нет.
    """
    if len(fast_ema) < 2 or len(slow_ema) < 2:
        return None

    # Предыдущий бар
    prev_fast = fast_ema[-2]
    prev_slow = slow_ema[-2]
    # Текущий бар
    curr_fast = fast_ema[-1]
    curr_slow = slow_ema[-1]

    # Бычье пересечение: fast был ниже slow, стал выше
    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return "LONG"

    # Медвежье пересечение: fast был выше slow, стал ниже
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return "SHORT"

    return None


# ─── Вспомогательные ──────────────────────────────────────────────────

_MOMENTUM_ADAPTER: ExchangeAdapter | None = None


def _get_adapter() -> ExchangeAdapter:
    """Адаптер биржи для momentum (кешируется)."""
    global _MOMENTUM_ADAPTER
    if _MOMENTUM_ADAPTER is None:
        _MOMENTUM_ADAPTER = get_adapter(cfg.MOMENTUM_EXCHANGE)
    return _MOMENTUM_ADAPTER


def _calc_position_size(state: dict[str, Any], price: float) -> float:
    """Размер позиции в base-монете.

    position_usdt = allocated_capital / max_positions * leverage
    qty = position_usdt / price
    """
    allocated = capital_allocator.get_strategy_capital(state, "momentum")
    per_position = allocated / max(1, cfg.MOMENTUM_MAX_POSITIONS)
    notional = per_position * cfg.MOMENTUM_LEVERAGE
    return notional / price if price > 0 else 0.0


def _get_symbol_exposure(state: dict[str, Any], symbol: str) -> float:
    """Суммарная нетто-экспозиция по символу по всем стратегиям (USDT).

    Grid: считаем кол-во filled buy - filled sell * mid_price * qty.
    Momentum: открытые позиции notional.
    """
    exposure = 0.0

    # Grid exposure
    grid_state = state.get("grid", {})
    sym_grid = grid_state.get("symbols", {}).get(symbol, {})
    levels_raw = sym_grid.get("levels", [])
    mid = float(sym_grid.get("mid_price", 0.0))
    for d in levels_raw:
        if d.get("filled", False):
            # Filled buy = long exposure, filled sell = short exposure
            qty = float(d.get("qty", 0))
            if d.get("side") == "Buy":
                exposure += qty * mid
            elif d.get("side") == "Sell":
                exposure -= qty * mid

    # Momentum exposure
    mom_state = state.get("momentum", {})
    for pos in mom_state.get("positions", []):
        if pos.get("status") == "OPEN" and pos.get("symbol") == symbol:
            notional = float(pos.get("notional_usdt", 0))
            if pos.get("side") == "LONG":
                exposure += notional
            else:
                exposure -= notional

    return abs(exposure)


def _is_daily_loss_exceeded(
    state: dict[str, Any], strategy: str, limit_pct: float
) -> bool:
    """Проверить, превышен ли дневной лимит убытков для стратегии.

    Считает PnL за текущие UTC-сутки из state["daily_pnl_{strategy}"].
    """
    if limit_pct <= 0:
        return False
    g = state.get("global", {})
    daily_key = f"daily_pnl_{strategy}"
    daily_pnl = float(g.get(daily_key, 0.0))
    equity = capital_allocator.get_current_equity(state)
    if equity <= 0:
        return False
    return daily_pnl <= -(equity * limit_pct)


# ─── Инициализация state ──────────────────────────────────────────────

def init_momentum_state(state: dict[str, Any]) -> None:
    """Инициализировать секцию momentum в state."""
    state.setdefault("momentum", {})
    mom = state["momentum"]
    mom.setdefault("enabled", cfg.MOMENTUM_ENABLED)
    mom.setdefault("positions", [])
    mom.setdefault("total_trades", 0)
    mom.setdefault("total_profit_usdt", 0.0)
    mom.setdefault("last_tick_epoch", 0.0)
    mom.setdefault("signals_history", [])


# ─── Основной тик ─────────────────────────────────────────────────────

async def momentum_tick(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Основной тик momentum-стратегии.

    Вызывается из main loop раз в MOMENTUM_TICK_INTERVAL_SEC.
    Возвращает dict с результатами.
    """
    # Проверяем global kill-switch
    if global_kill_switch.is_kill_active(state):
        return {"skipped": "global_kill_active"}

    mom_state = state.get("momentum", {})
    if not mom_state.get("enabled", False):
        return {"skipped": "momentum_disabled"}

    # Rate-limit
    last_tick = float(mom_state.get("last_tick_epoch", 0))
    now = time.time()
    if (now - last_tick) < cfg.MOMENTUM_TICK_INTERVAL_SEC:
        return {"skipped": "cooldown"}

    mom_state["last_tick_epoch"] = now

    adapter = _get_adapter()
    results: list[str] = []
    errors: list[str] = []

    for symbol in cfg.MOMENTUM_SYMBOLS:
        try:
            result = await _process_symbol(session, state, adapter, symbol)
            results.append(f"{symbol}: {result}")
        except Exception as exc:  # noqa: BLE001
            err_msg = f"{symbol}: {exc}"
            errors.append(err_msg)
            print(f"[MOMENTUM] Ошибка тика {symbol}: {exc}")

    return {"processed": results, "errors": errors}


async def _process_symbol(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    adapter: ExchangeAdapter,
    symbol: str,
) -> str:
    """Обработать один символ: сигнал + управление позицией."""
    mom_state = state["momentum"]

    # Получаем свечи
    klines = await adapter.get_klines(
        session, symbol, cfg.MOMENTUM_TIMEFRAME, limit=100
    )
    if not klines or len(klines) < cfg.MOMENTUM_EMA_SLOW + 5:
        return "недостаточно свечей"

    # Извлекаем close-цены
    closes = [float(k["close"]) for k in klines]

    # Считаем EMA
    fast_ema = calc_ema(closes, cfg.MOMENTUM_EMA_FAST)
    slow_ema = calc_ema(closes, cfg.MOMENTUM_EMA_SLOW)

    # Текущая цена
    current_price = closes[-1]

    # Проверяем существующую позицию по символу
    existing = _find_position(mom_state, symbol)

    if existing:
        # Управляем открытой позицией (trailing stop + выход)
        return await _manage_position(
            session, state, adapter, symbol, existing, fast_ema, slow_ema, current_price, klines
        )

    # Нет позиции — ищем сигнал
    signal = detect_crossover(fast_ema, slow_ema)
    if signal is None:
        return "нет сигнала"

    # #2: Confirmation bar — проверяем что кросс подтверждён закрытием
    # предыдущей свечи (не текущей). Смотрим на [-3:-1] вместо [-2:]
    if cfg.MOMENTUM_CONFIRMATION_BAR:
        # Проверяем кросс на предыдущем баре, а текущий бар подтверждает
        if len(fast_ema) >= 3 and len(slow_ema) >= 3:
            # Кросс должен был случиться на пред-предыдущем → предыдущем
            prev_signal = detect_crossover(fast_ema[:-1], slow_ema[:-1])
            if prev_signal != signal:
                # Кросс только на текущем баре — ждём confirmation
                # Сохраняем pending signal
                mom_state.setdefault("pending_signals", {})[symbol] = {
                    "signal": signal,
                    "epoch": time.time(),
                }
                return f"сигнал {signal}, ждём confirmation"
            # Проверяем pending — если был на прошлом тике и совпадает
            pending = mom_state.get("pending_signals", {}).get(symbol)
            if not pending or pending.get("signal") != signal:
                mom_state.setdefault("pending_signals", {})[symbol] = {
                    "signal": signal,
                    "epoch": time.time(),
                }
                return f"сигнал {signal}, ждём confirmation"
            # Confirmation получен — удаляем pending
            mom_state.get("pending_signals", {}).pop(symbol, None)

    # ATR-фильтр: не входим если волатильность слишком низкая (боковик)
    atr = calc_atr(klines, period=14)
    if current_price > 0 and atr / current_price < cfg.MOMENTUM_MIN_ATR_PCT:
        return f"сигнал {signal}, но ATR слишком мал ({atr/current_price*100:.2f}%)"

    # ADX filter: не входим если нет тренда
    if cfg.MOMENTUM_MIN_ADX > 0:
        adx = calc_adx(klines, period=14)
        if adx < cfg.MOMENTUM_MIN_ADX:
            return f"сигнал {signal}, но ADX слишком мал ({adx:.1f} < {cfg.MOMENTUM_MIN_ADX})"

    # RSI filter: не входим в перекупленность/перепроданность
    rsi = calc_rsi(closes, period=14)
    if signal == "LONG" and rsi > cfg.MOMENTUM_RSI_OVERBOUGHT:
        return f"сигнал LONG, но RSI перекуплен ({rsi:.1f} > {cfg.MOMENTUM_RSI_OVERBOUGHT})"
    if signal == "SHORT" and rsi < cfg.MOMENTUM_RSI_OVERSOLD:
        return f"сигнал SHORT, но RSI перепродан ({rsi:.1f} < {cfg.MOMENTUM_RSI_OVERSOLD})"

    # #6: Cross-strategy exposure check
    max_exposure = cfg.RISK_MAX_EXPOSURE_PER_SYMBOL_PCT
    if max_exposure > 0:
        equity = capital_allocator.get_current_equity(state)
        # Считаем текущую экспозицию по символу (grid + momentum)
        existing_exposure = _get_symbol_exposure(state, symbol)
        new_notional = _calc_position_size(state, current_price) * current_price
        if equity > 0 and (existing_exposure + new_notional) / equity > max_exposure:
            return f"сигнал {signal}, но exposure limit ({(existing_exposure + new_notional)/equity*100:.0f}%)"

    # Проверяем лимит позиций
    positions = mom_state.get("positions", [])
    open_count = sum(1 for p in positions if p.get("status") == "OPEN")
    if open_count >= cfg.MOMENTUM_MAX_POSITIONS:
        return f"сигнал {signal}, но макс. позиций ({cfg.MOMENTUM_MAX_POSITIONS})"

    # #7: Per-strategy daily loss check
    if _is_daily_loss_exceeded(state, "momentum", cfg.RISK_DAILY_LOSS_MOMENTUM_PCT):
        return f"сигнал {signal}, но daily loss limit"

    # #4: AI Signal scoring — фильтр слабых сигналов
    try:
        import ai_integration
        should_enter, score = ai_integration.score_momentum_entry(
            klines, fast_ema, slow_ema, signal, min_score=0.35
        )
        if not should_enter:
            return f"сигнал {signal}, но score={score:.2f} < 0.35"
    except Exception:  # noqa: BLE001
        score = 0.5  # fallback — входим без scoring

    # Spread guard: проверяем что ликвидность достаточная
    try:
        import runtime_state
        top = await adapter.get_orderbook_top(session, symbol)
        if top and runtime_state.is_spread_too_wide(top[0], top[1]):
            return f"сигнал {signal}, но spread слишком широкий"
    except Exception:  # noqa: BLE001
        pass

    # Correlation guard: не открывать в том же направлении по BTC если ETH уже LONG
    try:
        import runtime_state
        if not runtime_state.check_correlation_allows_entry(state, symbol, signal):
            return f"сигнал {signal}, но correlation guard (группа уже open)"
    except Exception:  # noqa: BLE001
        pass

    # Открываем позицию
    return await _open_position(
        session, state, adapter, symbol, signal, current_price, klines=klines
    )


def _find_position(mom_state: dict[str, Any], symbol: str) -> Optional[dict[str, Any]]:
    """Найти открытую позицию по символу."""
    positions = mom_state.get("positions", [])
    for pos in positions:
        if pos.get("symbol") == symbol and pos.get("status") == "OPEN":
            return pos
    return None


async def _open_position(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    adapter: ExchangeAdapter,
    symbol: str,
    signal: str,
    price: float,
    klines: list[dict[str, Any]] | None = None,
) -> str:
    """Открыть позицию по сигналу."""
    mom_state = state["momentum"]

    # Размер позиции
    qty = _calc_position_size(state, price)
    info = await adapter.get_instrument_info(session, symbol)
    if info is None:
        return "instrument_info недоступен"

    qty = adapter.validate_and_round_qty(qty, info, price)
    if qty <= 0:
        return "qty слишком мал"

    # Определяем side
    side = "Buy" if signal == "LONG" else "Sell"

    # Стоп-лосс и тейк-профит
    sl_pct = cfg.MOMENTUM_STOP_LOSS_PCT
    tp_pct = cfg.MOMENTUM_TAKE_PROFIT_PCT

    # ATR-based stops
    if cfg.MOMENTUM_USE_ATR_STOPS and klines:
        atr = calc_atr(klines, period=14)
        if atr > 0 and price > 0:
            atr_pct = atr / price
            sl_pct = atr_pct * cfg.MOMENTUM_ATR_SL_MULT
            tp_pct = atr_pct * cfg.MOMENTUM_ATR_TP_MULT

    if signal == "LONG":
        stop_loss = price * (1 - sl_pct)
        take_profit = price * (1 + tp_pct) if tp_pct > 0 else None
    else:
        stop_loss = price * (1 + sl_pct)
        take_profit = price * (1 - tp_pct) if tp_pct > 0 else None

    # Размещаем ордер
    result = await adapter.place_order_with_fallback(
        session,
        symbol=symbol,
        side=side,
        qty=qty,
        stop_loss=stop_loss,
        take_profit=take_profit,
        reduce_only=False,
    )

    if not result:
        return f"ордер {side} не исполнен"

    fill_price = float(result.get("fill_price", price))

    # Записываем позицию
    position = {
        "symbol": symbol,
        "side": signal,
        "entry_price": fill_price,
        "qty": qty,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "opened_epoch": time.time(),
        "status": "OPEN",
        "notional_usdt": qty * fill_price,
    }
    mom_state.setdefault("positions", []).append(position)

    # Записываем сигнал в историю
    mom_state.setdefault("signals_history", []).append({
        "symbol": symbol,
        "signal": signal,
        "price": fill_price,
        "epoch": time.time(),
    })
    # Лимитируем историю
    if len(mom_state["signals_history"]) > 50:
        mom_state["signals_history"] = mom_state["signals_history"][-50:]

    direction = "LONG ↗" if signal == "LONG" else "SHORT ↘"
    return f"ОТКРЫТО {direction} @{fill_price:.2f}, qty={qty}, SL={stop_loss:.2f}"


async def _manage_position(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    adapter: ExchangeAdapter,
    symbol: str,
    position: dict[str, Any],
    fast_ema: list[float],
    slow_ema: list[float],
    current_price: float,
    klines: list[dict[str, Any]] | None = None,
) -> str:
    """Управление открытой позицией: trailing stop + проверка выхода."""
    signal = detect_crossover(fast_ema, slow_ema)
    pos_side = position["side"]  # "LONG" или "SHORT"

    # Выход по обратному сигналу
    should_close = False
    close_reason = ""

    if pos_side == "LONG" and signal == "SHORT":
        should_close = True
        close_reason = "обратный сигнал (SHORT cross)"
    elif pos_side == "SHORT" and signal == "LONG":
        should_close = True
        close_reason = "обратный сигнал (LONG cross)"

    # Рассчитываем текущий PnL%
    entry = float(position["entry_price"])
    if pos_side == "LONG":
        pnl_pct = (current_price - entry) / entry
    else:
        pnl_pct = (entry - current_price) / entry

    # Trailing stop логика
    trail_activate = cfg.MOMENTUM_TRAIL_ACTIVATE_PCT
    trail_distance = cfg.MOMENTUM_TRAIL_DISTANCE_PCT
    current_sl = float(position.get("stop_loss", 0.0))

    if trail_activate > 0 and trail_distance > 0 and pnl_pct >= trail_activate:
        # Прибыль достигла порога — подтягиваем SL
        if pos_side == "LONG":
            new_sl = current_price * (1 - trail_distance)
            if new_sl > current_sl:
                # Обновляем SL на бирже
                result = await retry_async(
                    lambda _sl=new_sl: adapter.set_trading_stop(session, symbol, stop_loss=_sl),
                    max_retries=2, base_delay=0.5, label=f"trailing_SL_{symbol}",
                )
                if result is not None:
                    position["stop_loss"] = new_sl
        else:
            new_sl = current_price * (1 + trail_distance)
            if new_sl < current_sl or current_sl == 0:
                result = await retry_async(
                    lambda _sl=new_sl: adapter.set_trading_stop(session, symbol, stop_loss=_sl),
                    max_retries=2, base_delay=0.5, label=f"trailing_SL_{symbol}",
                )
                if result is not None:
                    position["stop_loss"] = new_sl

    # Проверка SL/TP (на случай если биржа не сработала)
    current_sl = float(position.get("stop_loss", 0.0))
    if pos_side == "LONG":
        if current_sl > 0 and current_price <= current_sl:
            should_close = True
            close_reason = f"стоп-лосс ({pnl_pct*100:.1f}%)"
        elif cfg.MOMENTUM_TAKE_PROFIT_PCT > 0 and pnl_pct >= cfg.MOMENTUM_TAKE_PROFIT_PCT:
            should_close = True
            close_reason = f"тейк-профит ({pnl_pct*100:.1f}%)"
    else:
        if current_sl > 0 and current_price >= current_sl:
            should_close = True
            close_reason = f"стоп-лосс ({pnl_pct*100:.1f}%)"
        elif cfg.MOMENTUM_TAKE_PROFIT_PCT > 0 and pnl_pct >= cfg.MOMENTUM_TAKE_PROFIT_PCT:
            should_close = True
            close_reason = f"тейк-профит ({pnl_pct*100:.1f}%)"

    if not should_close:
        # #6: Volume anomaly early exit
        try:
            import ai_integration
            if klines and ai_integration.check_volume_anomaly_exit(klines, pos_side):
                should_close = True
                close_reason = "volume anomaly (institutional exit)"
        except Exception:  # noqa: BLE001
            pass

    if not should_close:
        held_h = (time.time() - float(position.get("opened_epoch", 0))) / 3600
        trail_info = ""
        if trail_activate > 0 and pnl_pct >= trail_activate:
            trail_info = " [trail]"
        return f"держим {pos_side} ({held_h:.1f}ч, PnL {pnl_pct*100:+.1f}%{trail_info})"

    # Закрываем позицию
    return await _close_position(
        session, state, adapter, symbol, position, current_price, close_reason
    )


async def _close_position(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    adapter: ExchangeAdapter,
    symbol: str,
    position: dict[str, Any],
    current_price: float,
    reason: str,
) -> str:
    """Закрыть позицию."""
    mom_state = state["momentum"]
    pos_side = position["side"]
    qty = float(position["qty"])

    # Закрывающий ордер — противоположная сторона
    close_side = "Sell" if pos_side == "LONG" else "Buy"

    result = await adapter.place_order_with_fallback(
        session,
        symbol=symbol,
        side=close_side,
        qty=qty,
        reduce_only=True,
    )

    fill_price = current_price
    if result and result.get("fill_price"):
        fill_price = float(result["fill_price"])

    # PnL
    entry = float(position["entry_price"])
    if pos_side == "LONG":
        pnl_usdt = (fill_price - entry) * qty
    else:
        pnl_usdt = (entry - fill_price) * qty

    # С учётом leverage — PnL уже рассчитан правильно (qty масштабирован)
    capital_allocator.record_pnl(state, "momentum", pnl_usdt)

    # Обновляем позицию
    position["status"] = "CLOSED"
    position["exit_price"] = fill_price
    position["closed_epoch"] = time.time()
    position["pnl_usdt"] = pnl_usdt
    position["close_reason"] = reason

    # Счётчики
    mom_state["total_trades"] = int(mom_state.get("total_trades", 0)) + 1
    mom_state["total_profit_usdt"] = (
        float(mom_state.get("total_profit_usdt", 0.0)) + pnl_usdt
    )

    # Чистим закрытые позиции (оставляем последние 20 для истории)
    positions = mom_state.get("positions", [])
    closed = [p for p in positions if p.get("status") == "CLOSED"]
    if len(closed) > 20:
        # Удаляем самые старые закрытые
        closed_sorted = sorted(closed, key=lambda p: float(p.get("closed_epoch", 0)))
        to_remove = closed_sorted[:-20]
        mom_state["positions"] = [p for p in positions if p not in to_remove]

    arrow = "▲" if pnl_usdt >= 0 else "▼"
    return f"ЗАКРЫТО {pos_side} {arrow} {pnl_usdt:+.2f} USDT ({reason})"


# ─── Управление ───────────────────────────────────────────────────────

async def stop_momentum(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
) -> str:
    """Остановить momentum: закрыть все позиции."""
    mom_state = state.get("momentum", {})
    adapter = _get_adapter()
    closed_count = 0

    positions = mom_state.get("positions", [])
    for pos in positions:
        if pos.get("status") != "OPEN":
            continue
        symbol = pos["symbol"]
        try:
            top = await adapter.get_orderbook_top(session, symbol)
            price = (top[0] + top[1]) / 2 if top else float(pos["entry_price"])
            await _close_position(
                session, state, adapter, symbol, pos, price, "manual_stop"
            )
            closed_count += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[MOMENTUM] stop close {symbol}: {exc}")

    mom_state["enabled"] = False
    return f"Momentum остановлен. Закрыто позиций: {closed_count}."


async def start_momentum(state: dict[str, Any]) -> str:
    """Включить momentum-стратегию."""
    mom_state = state.setdefault("momentum", {})
    mom_state["enabled"] = True
    mom_state["last_tick_epoch"] = 0.0
    return "Momentum включен. Сигналы проверятся на следующем тике."


def get_momentum_status(state: dict[str, Any]) -> dict[str, Any]:
    """Статус momentum для UI."""
    mom_state = state.get("momentum", {})
    positions = mom_state.get("positions", [])
    open_positions = [p for p in positions if p.get("status") == "OPEN"]

    return {
        "enabled": mom_state.get("enabled", False),
        "open_positions": open_positions,
        "total_trades": int(mom_state.get("total_trades", 0)),
        "total_profit_usdt": float(mom_state.get("total_profit_usdt", 0.0)),
        "exchange": cfg.MOMENTUM_EXCHANGE,
        "ema_fast": cfg.MOMENTUM_EMA_FAST,
        "ema_slow": cfg.MOMENTUM_EMA_SLOW,
        "leverage": cfg.MOMENTUM_LEVERAGE,
        "timeframe": cfg.MOMENTUM_TIMEFRAME,
        "max_positions": cfg.MOMENTUM_MAX_POSITIONS,
        "signals_history": mom_state.get("signals_history", [])[-10:],
    }
