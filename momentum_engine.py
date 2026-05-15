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
    """Обработать один символ: regime-adaptive routing + управление позицией."""
    mom_state = state["momentum"]

    # Получаем свечи
    klines = await adapter.get_klines(
        session, symbol, cfg.MOMENTUM_TIMEFRAME, limit=100
    )
    if not klines or len(klines) < 50:
        return "недостаточно свечей"

    # Извлекаем close-цены
    closes = [float(k["close"]) for k in klines]

    # Текущая цена
    current_price = closes[-1]

    # Calculate ADX and RSI for regime routing
    adx = calc_adx(klines[-50:], period=14)
    rsi = calc_rsi(closes[-30:], period=14)

    # Проверяем существующую позицию по символу
    existing = _find_position(mom_state, symbol)

    if existing:
        # Управляем открытой позицией
        return await _manage_position(
            session, state, adapter, symbol, existing,
            closes, current_price, klines, rsi
        )

    # Нет позиции — regime-adaptive signal generation

    # Time-of-day filter: skip quiet hours
    if cfg.MOMENTUM_SESSION_FILTER_ENABLED:
        from datetime import datetime, timezone
        hour = datetime.now(tz=timezone.utc).hour
        if hour < cfg.MOMENTUM_SESSION_START_UTC or hour >= cfg.MOMENTUM_SESSION_END_UTC:
            return f"вне торговой сессии ({hour}:00 UTC)"

    # Equity curve protection: pause if losing streak
    # NOTE: This intentionally checks ALL symbols in aggregate (cross-symbol blocking).
    # BTC and ETH are highly correlated, so a losing streak on one symbol signals
    # adverse conditions for both. This is by design for a 2-symbol correlated portfolio.
    if cfg.MOMENTUM_EQUITY_CURVE_PROTECTION:
        positions = mom_state.get("positions", [])
        closed = [p for p in positions if p.get("status") == "CLOSED"]
        if len(closed) >= 5:
            recent_pnl = [float(p.get("pnl_usdt", 0)) for p in closed[-10:]]
            if len(recent_pnl) >= 5:
                recent_3 = sum(recent_pnl[-3:])
                cumulative = sum(recent_pnl)
                # If last 3 trades are net negative AND overall trend is down - pause
                if recent_3 < 0 and cumulative < 0:
                    return f"equity curve protection: losing streak (last3={recent_3:.2f}, cum10={cumulative:.2f})"

    # Regime routing
    signal = None
    strategy_type = "BO"

    if adx < cfg.MOMENTUM_ADX_RANGE_THRESHOLD:
        # Mean-Reversion regime: RSI extremes
        if rsi < cfg.MOMENTUM_MR_RSI_OVERSOLD:
            signal = "LONG"
            strategy_type = "MR"
        elif rsi > cfg.MOMENTUM_MR_RSI_OVERBOUGHT:
            signal = "SHORT"
            strategy_type = "MR"
    elif adx >= cfg.MOMENTUM_ADX_TREND_THRESHOLD:
        # Breakout regime: price breaks N-bar high/low with volume confirmation
        lookback = cfg.MOMENTUM_BO_LOOKBACK
        if len(klines) > lookback + 1:
            window = klines[-lookback - 1:-1]
            window_highs = [float(k["high"]) for k in window]
            window_lows = [float(k["low"]) for k in window]
            window_volumes = [float(k.get("volume", 0)) for k in window]
            avg_vol = sum(window_volumes) / len(window_volumes) if window_volumes else 0
            current_high = float(klines[-1]["high"])
            current_low = float(klines[-1]["low"])
            current_vol = float(klines[-1].get("volume", 0))
            vol_ok = avg_vol > 0 and current_vol > avg_vol * cfg.MOMENTUM_BO_MIN_VOL_RATIO

            if current_high > max(window_highs) and vol_ok:
                signal = "LONG"
                strategy_type = "BO"
            elif current_low < min(window_lows) and vol_ok:
                signal = "SHORT"
                strategy_type = "BO"
    else:
        # Dead zone: ADX_RANGE_THRESHOLD <= ADX < ADX_TREND_THRESHOLD
        return f"ADX dead zone ({adx:.1f}), skip"

    if signal is None:
        return "нет сигнала"

    # --- MR-specific filters ---

    if strategy_type == "MR":
        # RSI momentum filter: не входить если RSI резко падает/растёт (начало тренда, не reversion)
        if adx < cfg.MOMENTUM_ADX_RANGE_THRESHOLD:
            if len(closes) > 33:
                rsi_prev = calc_rsi(closes[max(0, len(closes) - 33):len(closes) - 3], 14)
                rsi_delta = rsi - rsi_prev
                # Если RSI падает быстро -> не LONG (это breakdown, не reversion)
                # Если RSI растёт быстро -> не SHORT
                if signal == "LONG" and rsi_delta < -cfg.MOMENTUM_MR_RSI_DELTA_THRESHOLD:
                    return f"сигнал LONG, но RSI momentum слишком сильный ({rsi_delta:+.0f})"
                if signal == "SHORT" and rsi_delta > cfg.MOMENTUM_MR_RSI_DELTA_THRESHOLD:
                    return f"сигнал SHORT, но RSI momentum слишком сильный ({rsi_delta:+.0f})"

        # Volume confirmation: вход только при повышенном volume (capitulation, не drift)
        if cfg.MOMENTUM_MR_MIN_VOL_RATIO > 0 and len(klines) > 21:
            volumes = [float(k.get("volume", 0)) for k in klines[-21:-1]]
            avg_vol = sum(volumes) / len(volumes) if volumes else 0
            cur_vol = float(klines[-1].get("volume", 0))
            if avg_vol > 0 and cur_vol < avg_vol * cfg.MOMENTUM_MR_MIN_VOL_RATIO:
                return f"сигнал {signal}, но volume слишком низкий ({cur_vol/avg_vol:.1f}x < {cfg.MOMENTUM_MR_MIN_VOL_RATIO}x)"

        # BB width check: MR лучше работает при сжатых BB (range-bound)
        if cfg.MOMENTUM_MR_MAX_BB_WIDTH > 0:
            from regime_classifier import calc_bb_width
            bb_w = calc_bb_width(closes[-20:], period=20)
            if bb_w > cfg.MOMENTUM_MR_MAX_BB_WIDTH:
                return f"сигнал {signal}, но BB width слишком широкий ({bb_w*100:.1f}% > {cfg.MOMENTUM_MR_MAX_BB_WIDTH*100:.0f}%)"

    # --- Guards ---

    # Cross-strategy exposure check
    max_exposure = cfg.RISK_MAX_EXPOSURE_PER_SYMBOL_PCT
    if max_exposure > 0:
        equity = capital_allocator.get_current_equity(state)
        existing_exposure = _get_symbol_exposure(state, symbol)
        new_notional = _calc_position_size(state, current_price) * current_price
        if equity > 0 and (existing_exposure + new_notional) / equity > max_exposure:
            return f"сигнал {signal}, но exposure limit ({(existing_exposure + new_notional)/equity*100:.0f}%)"

    # Проверяем лимит позиций
    positions = mom_state.get("positions", [])
    open_count = sum(1 for p in positions if p.get("status") == "OPEN")
    if open_count >= cfg.MOMENTUM_MAX_POSITIONS:
        return f"сигнал {signal}, но макс. позиций ({cfg.MOMENTUM_MAX_POSITIONS})"

    # Per-strategy daily loss check
    if _is_daily_loss_exceeded(state, "momentum", cfg.RISK_DAILY_LOSS_MOMENTUM_PCT):
        return f"сигнал {signal}, но daily loss limit"

    # Macro calendar blackout check
    if cfg.MACRO_CALENDAR_ENABLED:
        try:
            import macro_calendar
            from datetime import datetime, timezone
            is_blackout, event_name = macro_calendar.is_macro_blackout(datetime.now(tz=timezone.utc))
            if is_blackout:
                return f"сигнал {signal}, но macro blackout ({event_name})"
        except Exception:
            pass

    # Spread guard
    try:
        import runtime_state
        top = await adapter.get_orderbook_top(session, symbol)
        if top and runtime_state.is_spread_too_wide(top[0], top[1]):
            return f"сигнал {signal}, но spread слишком широкий"
    except Exception:  # noqa: BLE001
        pass

    # Correlation guard
    try:
        import runtime_state
        if not runtime_state.check_correlation_allows_entry(state, symbol, signal):
            return f"сигнал {signal}, но correlation guard (группа уже open)"
    except Exception:  # noqa: BLE001
        pass

    # Открываем позицию
    return await _open_position(
        session, state, adapter, symbol, signal, current_price,
        klines=klines, strategy_type=strategy_type
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
    strategy_type: str = "BO",
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

    # Strategy-specific stop-loss
    if strategy_type == "MR":
        # Dynamic SL: max(fixed SL, ATR * 1.5)
        atr = calc_atr(klines[-20:], period=14) if klines else 0
        atr_sl = (atr / price * 1.5) if price > 0 and atr > 0 else 0
        sl_pct = max(cfg.MOMENTUM_MR_SL_PCT, atr_sl)
    else:
        sl_pct = cfg.MOMENTUM_BO_SL_PCT

    if signal == "LONG":
        stop_loss = price * (1 - sl_pct)
    else:
        stop_loss = price * (1 + sl_pct)

    take_profit = None  # Exits handled by _manage_position

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

    # Slippage tracking
    slippage_pct = abs(fill_price - price) / price if price > 0 else 0
    if slippage_pct > 0.001:  # > 0.1%
        print(f"[MOMENTUM] HIGH SLIPPAGE {symbol}: expected={price:.2f} got={fill_price:.2f} slip={slippage_pct*100:.2f}%")

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
        "slippage_pct": slippage_pct,
        "strategy_type": strategy_type,
    }
    mom_state.setdefault("positions", []).append(position)

    # Записываем сигнал в историю
    mom_state.setdefault("signals_history", []).append({
        "symbol": symbol,
        "signal": signal,
        "price": fill_price,
        "epoch": time.time(),
        "strategy_type": strategy_type,
    })
    # Лимитируем историю
    if len(mom_state["signals_history"]) > 50:
        mom_state["signals_history"] = mom_state["signals_history"][-50:]

    direction = "LONG ↗" if signal == "LONG" else "SHORT ↘"
    return f"ОТКРЫТО {direction} [{strategy_type}] @{fill_price:.2f}, qty={qty}, SL={stop_loss:.2f}"


async def _manage_position(
    session: aiohttp.ClientSession,
    state: dict[str, Any],
    adapter: ExchangeAdapter,
    symbol: str,
    position: dict[str, Any],
    closes: list[float],
    current_price: float,
    klines: list[dict[str, Any]] | None = None,
    rsi: float = 50.0,
) -> str:
    """Управление открытой позицией: regime-adaptive exits."""
    pos_side = position["side"]  # "LONG" или "SHORT"
    entry = float(position["entry_price"])
    strategy_type = position.get("strategy_type", "BO")

    # Рассчитываем текущий PnL%
    if pos_side == "LONG":
        pnl_pct = (current_price - entry) / entry
    else:
        pnl_pct = (entry - current_price) / entry

    # SL check (common for both strategies)
    current_sl = float(position.get("stop_loss", 0.0))
    should_close = False
    close_reason = ""

    if pos_side == "LONG" and current_sl > 0 and current_price <= current_sl:
        should_close = True
        close_reason = f"стоп-лосс ({pnl_pct*100:.1f}%)"
    elif pos_side == "SHORT" and current_sl > 0 and current_price >= current_sl:
        should_close = True
        close_reason = f"стоп-лосс ({pnl_pct*100:.1f}%)"

    if not should_close and strategy_type == "MR":
        # Break-even: если набрали +0.5% — перемещаем SL на entry
        if pnl_pct >= 0.005 and current_sl < entry and pos_side == "LONG":
            position["stop_loss"] = entry
            try:
                await adapter.set_trading_stop(session, symbol, stop_loss=entry)
            except Exception:
                pass
        elif pnl_pct >= 0.005 and current_sl > entry and pos_side == "SHORT":
            position["stop_loss"] = entry
            try:
                await adapter.set_trading_stop(session, symbol, stop_loss=entry)
            except Exception:
                pass

        # RSI reversion exit
        rsi_exit_long = cfg.MOMENTUM_MR_TP_RSI_EXIT
        rsi_exit_short = 100 - cfg.MOMENTUM_MR_TP_RSI_EXIT
        if pos_side == "LONG" and rsi > rsi_exit_long:
            should_close = True
            close_reason = f"RSI reversion ({rsi:.1f} > {rsi_exit_long:.0f})"
        elif pos_side == "SHORT" and rsi < rsi_exit_short:
            should_close = True
            close_reason = f"RSI reversion ({rsi:.1f} < {rsi_exit_short:.0f})"

        # Time stop
        if not should_close:
            opened_epoch = float(position.get("opened_epoch", 0))
            bar_seconds = int(cfg.MOMENTUM_TIMEFRAME) * 60
            bars_held = int((time.time() - opened_epoch) / bar_seconds)
            if bars_held > cfg.MOMENTUM_MR_MAX_HOLD_BARS:
                should_close = True
                close_reason = f"time stop ({bars_held} bars > {cfg.MOMENTUM_MR_MAX_HOLD_BARS})"

    if not should_close and strategy_type == "BO":
        # Trailing stop logic
        trail_activate = cfg.MOMENTUM_BO_TRAIL_ACTIVATE_PCT
        trail_distance = cfg.MOMENTUM_BO_TRAIL_DISTANCE_PCT

        if pnl_pct >= trail_activate:
            if pos_side == "LONG":
                new_sl = current_price * (1 - trail_distance)
                if new_sl > current_sl:
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

        # BO max hold time stop
        if not should_close:
            opened_epoch = float(position.get("opened_epoch", 0))
            bar_seconds = int(cfg.MOMENTUM_TIMEFRAME) * 60
            bars_held = int((time.time() - opened_epoch) / bar_seconds)
            if bars_held > cfg.MOMENTUM_BO_MAX_HOLD_BARS:
                should_close = True
                close_reason = f"BO time stop ({bars_held} bars > {cfg.MOMENTUM_BO_MAX_HOLD_BARS})"

    if not should_close:
        held_h = (time.time() - float(position.get("opened_epoch", 0))) / 3600
        return f"держим {pos_side} [{strategy_type}] ({held_h:.1f}ч, PnL {pnl_pct*100:+.1f}%)"

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
