"""Стратегия и индикаторы (чистый Python, без тяжёлых библиотек).

Правила входа:
  LONG  = close > EMA(200)  AND  RSI(14) пересек 30 снизу вверх на последнем баре
  SHORT = close < EMA(200)  AND  RSI(14) пересек 70 сверху вниз на последнем баре

Управление позицией:
  - Безубыток (breakeven) активируется при нереализованной прибыли >= +1.0%.
  - Трейлинг-TP активируется при +1.5% и далее подтягивается за high-water mark.

Функция evaluate_signal(klines) принимает список свечей Bybit V5
(каждая свеча = список строк: [start, open, high, low, close, volume, turnover])
и возвращает словарь с торговым сигналом или None.
"""

from __future__ import annotations

from typing import Any, Optional


# --- Индикаторы ---

def ema(values: list[float], period: int) -> list[float]:
    """Экспоненциальная скользящая средняя. Возвращает список той же длины,
    где до набора первого полного окна стоит None. Сид - простое SMA по
    первым `period` значениям, затем классическая EMA с alpha = 2/(period+1)."""
    if period <= 0:
        return [None for _ in values]  # type: ignore[list-item]
    if len(values) < period:
        return [None for _ in values]  # type: ignore[list-item]

    alpha = 2.0 / (period + 1.0)
    out: list[float] = [None] * len(values)  # type: ignore[list-item]
    sma = sum(values[:period]) / period
    out[period - 1] = sma
    prev = sma
    for i in range(period, len(values)):
        prev = alpha * values[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out


def rsi(values: list[float], period: int = 14) -> list[float]:
    """Классический Уайлдеровский RSI (сглаживание средним по Уайлдеру).
    Возвращает список той же длины, где до накопления данных стоят None."""
    n = len(values)
    out: list[float] = [None] * n  # type: ignore[list-item]
    if period <= 0 or n <= period:
        return out

    gains: list[float] = [0.0] * n
    losses: list[float] = [0.0] * n
    for i in range(1, n):
        change = values[i] - values[i - 1]
        gains[i] = change if change > 0 else 0.0
        losses[i] = -change if change < 0 else 0.0

    # Первое среднее - обычное арифметическое по окну `period`.
    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    if avg_loss == 0:
        out[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100.0 - (100.0 / (1.0 + rs))

    # Дальше - сглаживание Уайлдера.
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float]:
    """Average True Range по методу Уайлдера."""
    n = len(closes)
    out: list[float] = [None] * n  # type: ignore[list-item]
    if n < period + 1 or not (len(highs) == len(lows) == n):
        return out

    trs: list[float] = [0.0] * n
    trs[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs[i] = tr

    first_atr = sum(trs[1 : period + 1]) / period
    out[period] = first_atr
    prev = first_atr
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + trs[i]) / period
        out[i] = prev
    return out


# --- Вспомогательные функции управления позицией ---

def compute_breakeven(entry: float, current_price: float, side: str) -> bool:
    """True если нереализованная прибыль >= +1.0% (пора двигать SL в безубыток)."""
    if entry <= 0:
        return False
    if side.lower() in ("long", "buy"):
        pnl_pct = (current_price - entry) / entry
    else:
        pnl_pct = (entry - current_price) / entry
    return pnl_pct >= 0.01


def compute_trailing_tp(
    entry: float,
    current_price: float,
    prior_trail: Optional[float],
    side: str,
) -> Optional[float]:
    """Вернуть новый уровень трейлинг-TP, если активирован (+1.5% от входа).
    Трейлим за high-water mark (для LONG - вверх, для SHORT - вниз).
    Если ещё не активирован - возвращаем None."""
    if entry <= 0:
        return None
    is_long = side.lower() in ("long", "buy")
    if is_long:
        pnl_pct = (current_price - entry) / entry
    else:
        pnl_pct = (entry - current_price) / entry

    if pnl_pct < 0.015:
        return None

    if is_long:
        # Триггер ниже текущей цены примерно на 0.5% (half of activation move).
        candidate = current_price * (1.0 - 0.005)
        if prior_trail is None:
            return candidate
        return max(prior_trail, candidate)
    else:
        candidate = current_price * (1.0 + 0.005)
        if prior_trail is None:
            return candidate
        return min(prior_trail, candidate)


# --- Парсинг и основная функция оценки сигнала ---

def _extract_ohlc(klines: list[list[Any]]) -> tuple[list[float], list[float], list[float]]:
    """Разобрать свечи Bybit V5 в списки highs/lows/closes (float)."""
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    for k in klines:
        try:
            # Порядок Bybit: [start, open, high, low, close, volume, turnover]
            highs.append(float(k[2]))
            lows.append(float(k[3]))
            closes.append(float(k[4]))
        except (IndexError, TypeError, ValueError):
            continue
    return highs, lows, closes


def evaluate_signal(klines: list[list[Any]]) -> dict[str, Any]:
    """Оценить последний бар и вернуть торговый сигнал (или None).

    Возврат:
        {
            'signal': 'LONG' | 'SHORT' | None,
            'reason': str,
            'indicators': {'ema200': float, 'rsi': float, 'rsi_prev': float, 'atr': float, 'close': float},
            'entry': float,
            'sl': float,
            'tp': float,
        }
    """
    result: dict[str, Any] = {
        "signal": None,
        "reason": "",
        "indicators": {},
        "entry": 0.0,
        "sl": 0.0,
        "tp": 0.0,
    }

    highs, lows, closes = _extract_ohlc(klines)
    if len(closes) < 210:
        result["reason"] = "Недостаточно свечей для расчёта индикаторов"
        return result

    ema200_series = ema(closes, 200)
    rsi_series = rsi(closes, 14)
    atr_series = atr(highs, lows, closes, 14)

    ema200 = ema200_series[-1]
    rsi_cur = rsi_series[-1]
    rsi_prev = rsi_series[-2]
    atr_val = atr_series[-1]
    close = closes[-1]

    if ema200 is None or rsi_cur is None or rsi_prev is None or atr_val is None:
        result["reason"] = "Индикаторы не рассчитаны (мало данных)"
        return result

    result["indicators"] = {
        "ema200": ema200,
        "rsi": rsi_cur,
        "rsi_prev": rsi_prev,
        "atr": atr_val,
        "close": close,
    }

    # Пересечения RSI.
    crossed_up_from_below_30 = rsi_prev < 30.0 <= rsi_cur
    crossed_down_from_above_70 = rsi_prev > 70.0 >= rsi_cur

    sl_distance = 1.5 * atr_val
    tp_distance = 2.0 * atr_val

    if close > ema200 and crossed_up_from_below_30:
        entry = close
        sl = entry - sl_distance
        tp = entry + tp_distance
        result.update(
            signal="LONG",
            reason="Цена выше EMA200 и RSI(14) пересёк 30 снизу вверх",
            entry=entry,
            sl=sl,
            tp=tp,
        )
        return result

    if close < ema200 and crossed_down_from_above_70:
        entry = close
        sl = entry + sl_distance
        tp = entry - tp_distance
        result.update(
            signal="SHORT",
            reason="Цена ниже EMA200 и RSI(14) пересёк 70 сверху вниз",
            entry=entry,
            sl=sl,
            tp=tp,
        )
        return result

    result["reason"] = "Нет пересечения RSI на последнем баре"
    return result


def position_size(
    equity: float,
    entry: float,
    stop_loss: float,
    risk_per_trade: float,
) -> float:
    """Рассчитать размер позиции в контрактах по риску на сделку (R)."""
    if equity <= 0 or entry <= 0:
        return 0.0
    risk_amount = equity * max(risk_per_trade, 0.0)
    price_distance = abs(entry - stop_loss)
    if price_distance <= 0:
        return 0.0
    qty = risk_amount / price_distance
    # Округляем до 3 знаков - достаточно для BTCUSDT perpetual.
    return round(qty, 3)


# --- Заглушки для совместимости с бэктестером ---

STRATEGY_NAME = "strategy_v1"
SUPPORTED_TIMEFRAMES = ("15m",)


def on_bar(ctx):
    """Заглушка: strategy_v1 не реализует интерфейс бэктестера v2."""
    return None


def on_fill(ctx, fill):
    """Заглушка: strategy_v1 не реализует интерфейс бэктестера v2."""
    pass


def set_params(**kwargs):
    """Заглушка: strategy_v1 не поддерживает динамическую настройку параметров."""
    pass
