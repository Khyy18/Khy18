"""Technical indicators: EMA, ATR.

Used by grid_engine for adaptive step and trend bias calculations.
"""

from __future__ import annotations

from typing import Any


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
            # До набора полного окна -- простое среднее
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
