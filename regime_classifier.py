"""AI-классификатор режима рынка (без heavy deps).

Определяет текущий режим для каждого символа:
  TRENDING  — сильный тренд (ADX > 25, ATR высокий)
  RANGING   — боковик (ADX < 20, BB width узкий)
  VOLATILE  — высокая волатильность без направления

На основе режима combo_main маршрутизирует стратегии:
  TRENDING  → momentum ON, grid OFF (или сильный bias)
  RANGING   → grid ON, momentum OFF
  VOLATILE  → обе с уменьшенным size

Фичи:
  - ADX(14): сила тренда (0-100). >25 = тренд, <20 = боковик.
  - ATR/price: нормализованная волатильность.
  - BB width: (upper - lower) / mid. Узкий = сжатие = боковик.
  - Volume ratio: current / SMA(20). >1.5 = активность.

Decision tree на порогах (калибруются бэктестом).
"""

from __future__ import annotations

from typing import Any


# ─── Индикаторы (stdlib only) ──────────────────────────────────────────

def calc_adx(klines: list[dict[str, Any]], period: int = 14) -> float:
    """Average Directional Index. Упрощённая реализация.

    Возвращает ADX (0-100). 0 при недостатке данных.
    """
    if len(klines) < period * 2 + 1:
        return 0.0

    # Считаем +DM, -DM, TR
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    tr_list: list[float] = []

    for i in range(1, len(klines)):
        high = float(klines[i]["high"])
        low = float(klines[i]["low"])
        prev_high = float(klines[i - 1]["high"])
        prev_low = float(klines[i - 1]["low"])
        prev_close = float(klines[i - 1]["close"])

        # True Range
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)

        # Directional Movement
        up_move = high - prev_high
        down_move = prev_low - low

        if up_move > down_move and up_move > 0:
            plus_dm.append(up_move)
        else:
            plus_dm.append(0.0)

        if down_move > up_move and down_move > 0:
            minus_dm.append(down_move)
        else:
            minus_dm.append(0.0)

    # Smoothed averages (Wilder's smoothing = EMA с period)
    def wilder_smooth(data: list[float], p: int) -> list[float]:
        if len(data) < p:
            return []
        smoothed = [sum(data[:p])]
        for i in range(p, len(data)):
            smoothed.append(smoothed[-1] - smoothed[-1] / p + data[i])
        return smoothed

    sm_tr = wilder_smooth(tr_list, period)
    sm_plus = wilder_smooth(plus_dm, period)
    sm_minus = wilder_smooth(minus_dm, period)

    if not sm_tr or not sm_plus or not sm_minus:
        return 0.0

    # DI+ и DI-
    n = min(len(sm_tr), len(sm_plus), len(sm_minus))
    dx_list: list[float] = []
    for i in range(n):
        if sm_tr[i] == 0:
            continue
        di_plus = 100 * sm_plus[i] / sm_tr[i]
        di_minus = 100 * sm_minus[i] / sm_tr[i]
        di_sum = di_plus + di_minus
        if di_sum == 0:
            dx_list.append(0.0)
        else:
            dx_list.append(100 * abs(di_plus - di_minus) / di_sum)

    if len(dx_list) < period:
        return sum(dx_list) / len(dx_list) if dx_list else 0.0

    # ADX = SMA(DX, period)
    adx = sum(dx_list[-period:]) / period
    return adx


def calc_bb_width(closes: list[float], period: int = 20) -> float:
    """Bollinger Band width = (upper - lower) / mid.

    Возвращает 0.0 при недостатке данных.
    """
    if len(closes) < period:
        return 0.0

    window = closes[-period:]
    sma = sum(window) / period
    if sma == 0:
        return 0.0

    # Стандартное отклонение
    variance = sum((x - sma) ** 2 for x in window) / period
    std = variance ** 0.5

    upper = sma + 2 * std
    lower = sma - 2 * std
    width = (upper - lower) / sma
    return width


def calc_volume_ratio(klines: list[dict[str, Any]], period: int = 20) -> float:
    """Текущий volume / SMA(volume, period).

    >1.5 = повышенная активность. <0.5 = затишье.
    """
    if len(klines) < period + 1:
        return 1.0

    volumes = [float(k.get("volume", 0)) for k in klines]
    if not volumes:
        return 1.0

    current_vol = volumes[-1]
    avg_vol = sum(volumes[-period - 1:-1]) / period
    if avg_vol == 0:
        return 1.0

    return current_vol / avg_vol


# ─── Классификатор ─────────────────────────────────────────────────────

class MarketRegime:
    """Результат классификации режима рынка."""
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"


def classify_regime(
    klines: list[dict[str, Any]],
    adx_trend_threshold: float = 25.0,
    adx_range_threshold: float = 20.0,
    bb_narrow_threshold: float = 0.03,
    vol_ratio_high: float = 1.5,
) -> dict[str, Any]:
    """Классифицировать текущий режим рынка.

    Возвращает:
        {
            "regime": "TRENDING" | "RANGING" | "VOLATILE",
            "adx": float,
            "bb_width": float,
            "volume_ratio": float,
            "atr_pct": float,
            "confidence": float (0-1),
        }
    """
    from momentum_engine import calc_atr

    closes = [float(k["close"]) for k in klines]
    current_price = closes[-1] if closes else 0.0

    # Считаем индикаторы
    adx = calc_adx(klines, period=14)
    bb_width = calc_bb_width(closes, period=20)
    vol_ratio = calc_volume_ratio(klines, period=20)
    atr = calc_atr(klines, period=14)
    atr_pct = atr / current_price if current_price > 0 else 0.0

    # Decision tree
    regime = MarketRegime.RANGING
    confidence = 0.5

    if adx >= adx_trend_threshold:
        # Сильный ADX = тренд
        regime = MarketRegime.TRENDING
        confidence = min(1.0, (adx - adx_trend_threshold) / 20.0 + 0.5)
    elif adx <= adx_range_threshold and bb_width < bb_narrow_threshold:
        # Низкий ADX + узкие BB = чистый боковик
        regime = MarketRegime.RANGING
        confidence = min(1.0, (adx_range_threshold - adx) / 10.0 + 0.5)
    elif vol_ratio > vol_ratio_high and atr_pct > 0.01:
        # Высокий volume + высокий ATR без тренда = volatile
        regime = MarketRegime.VOLATILE
        confidence = min(1.0, vol_ratio / 3.0)
    elif adx < adx_range_threshold:
        regime = MarketRegime.RANGING
        confidence = 0.6
    else:
        # Промежуточная зона — слабый тренд
        regime = MarketRegime.TRENDING
        confidence = 0.4

    return {
        "regime": regime,
        "adx": adx,
        "bb_width": bb_width,
        "volume_ratio": vol_ratio,
        "atr_pct": atr_pct,
        "confidence": confidence,
    }


def should_enable_grid(regime_info: dict[str, Any]) -> bool:
    """Grid включён в RANGING и VOLATILE."""
    return regime_info["regime"] in (MarketRegime.RANGING, MarketRegime.VOLATILE)


def should_enable_momentum(regime_info: dict[str, Any]) -> bool:
    """Momentum включён в TRENDING и VOLATILE."""
    return regime_info["regime"] in (MarketRegime.TRENDING, MarketRegime.VOLATILE)


def get_size_multiplier(regime_info: dict[str, Any]) -> float:
    """Множитель размера позиции в зависимости от режима.

    VOLATILE → 0.5x (уменьшаем risk)
    TRENDING/RANGING → 1.0x (полный размер)
    """
    if regime_info["regime"] == MarketRegime.VOLATILE:
        return 0.5
    return 1.0
