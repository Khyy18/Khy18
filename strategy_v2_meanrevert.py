"""Стратегия v2 (подсистема) - Bollinger Bands mean-reversion на 15m.

Предназначение:
  Донабор сигналов в режиме RANGING, когда донcheev-стратегия (strategy_v2)
  простаивает. Основная идея - цена в боковике отскакивает от крайних
  полос Боллинджера к среднему, если нет тренда по ADX.

Правила входа (все одновременно; fail-CLOSED на неизвестном режиме):
  LONG  - regime == "RANGING", нет blackout,
          close_15m <= lower_band (BB 20/2),
          RSI(14) < 30,
          ADX(14) < 25 (иначе идёт тренд - mean-reversion опасна),
          ATR(15m) / close_15m >= MIN_ATR_PCT[symbol] / 2
          (половина часового порога: на 15m ATR меньше, чем на 1h,
          но контекст «подзаряженный» боковик остаётся).
  SHORT - симметрично: close_15m >= upper_band, RSI(14) > 70,
          остальные условия те же.

Выход:
  TP = middle band (SMA20) - возврат к среднему.
  hard_stop = entry -/+ 1.5 * ATR(15m).

Сайзинг:
  Риск на сделку = config.RISK_PER_TRADE * 0.5 (в два раза меньше, чем у
  Donchian: сделок будет больше, R короче, но winrate ожидается выше).
  qty = (equity * risk_per_trade) / stop_distance.

Индикаторы реализованы на чистом Python (list + statistics) идентично
тому, как они считаются в strategy_v1/strategy_v2: никаких numpy/pandas.
RSI(14) переиспользуется из strategy_v1.rsi; ATR(14) и ADX(14) - из
strategy_v2.atr / strategy_v2.adx. Bollinger Bands считаются здесь же
прямым циклом по окну 20.
"""

from __future__ import annotations

import statistics
from typing import Any, Optional

import config
from strategy_v1 import rsi
from strategy_v2 import adx, atr


STRATEGY_NAME = "strategy_v2_meanrevert"
SUPPORTED_TIMEFRAMES = ("15m",)

# Параметры BB/RSI/ADX/ATR по умолчанию.
_BB_PERIOD = 20
_BB_STD_MULT = 2.0
_RSI_PERIOD = 14
_ADX_PERIOD = 14
_ATR_PERIOD = 14
_RSI_OVERSOLD = 30.0
_RSI_OVERBOUGHT = 70.0
_ADX_RANGE_MAX = 25.0
_ATR_STOP_MULT = 1.5

# Теги вето (закрытый набор для rejected_checks и кнопки «ПОЧЕМУ МИМО?»).
_FILTER_TAGS = (
    "mr_regime_not_ranging",
    "mr_blackout",
    "mr_insufficient_data",
    "mr_no_band_touch",
    "mr_rsi_neutral",
    "mr_adx_trending",
    "mr_vol_low",
)


# --- Индикаторы --------------------------------------------------------------

def bollinger_bands(
    closes: list[float],
    period: int = _BB_PERIOD,
    std_mult: float = _BB_STD_MULT,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Полосы Боллинджера по последнему окну `period` баров.

    Возвращает (lower, middle, upper). Если данных меньше окна - None.
    """
    if period <= 0 or len(closes) < period:
        return None, None, None
    window = [float(c) for c in closes[-period:]]
    middle = sum(window) / period
    try:
        # statistics.pstdev - популяционный stdev (делим на N, а не N-1).
        # BB традиционно считают популяционным, это согласуется с TradingView.
        sd = statistics.pstdev(window)
    except statistics.StatisticsError:
        return None, None, None
    upper = middle + std_mult * sd
    lower = middle - std_mult * sd
    return lower, middle, upper


# --- Внутренние помощники ----------------------------------------------------

def _extract(candles: list[dict[str, Any]]) -> tuple[list[float], list[float], list[float]]:
    """Разобрать список свечей в (highs, lows, closes)."""
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    for c in candles:
        try:
            highs.append(float(c["high"]))
            lows.append(float(c["low"]))
            closes.append(float(c["close"]))
        except (KeyError, TypeError, ValueError):
            continue
    return highs, lows, closes


def _veto(
    tag: str,
    reason: str,
    indicators: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Сформировать отказной результат для evaluate_signal."""
    return {
        "signal": None,
        "reason": reason,
        "filter": tag if tag in _FILTER_TAGS else "mr_insufficient_data",
        "entry": 0.0,
        "sl": 0.0,
        "qty": 0.0,
        "indicators": indicators or {},
    }


def _min_atr_pct_for(symbol: str) -> float:
    """Половина часового порога волатильности для 15m-таймфрейма.

    На 15m абсолютный ATR меньше, чем на 1h, но нам нужен сигнал «рынок
    живой» - не абсолютная величина. Половина часового порога -
    прагматичный компромисс: отсекает полные штили, не отрезая нормальные
    боковики. Если символа нет в MIN_ATR_PCT, используется глобальный
    MIN_ATR_PCT_DEFAULT.
    """
    min_atr_map = getattr(config, "MIN_ATR_PCT", {}) or {}
    min_atr_default = float(
        getattr(config, "MIN_ATR_PCT_DEFAULT", 0.003) or 0.003
    )
    hourly = float(min_atr_map.get(symbol, min_atr_default))
    return hourly * 0.5


# --- Публичная логика сигнала ------------------------------------------------

def evaluate_signal(ctx: dict[str, Any]) -> dict[str, Any]:
    """Оценить последний закрытый 15m-бар и вернуть LONG/SHORT или вето.

    Формат ctx:
      {
        'symbol': str,
        'candles_15m': list[dict],    # обязательно
        'candles_1h':  list[dict],    # не используется, но допустимо
        'candles_4h':  list[dict],    # не используется
        'candles_1d':  list[dict],    # не используется
        'equity': float,
        'blackout': bool,
        'regime':   str,              # 'TRENDING'|'RANGING'|'CRISIS'
      }
    Все candles_15m содержат ПОСЛЕДНИЕ ЗАКРЫТЫЕ свечи (формирующийся
    бар должен быть отброшен вызывающей стороной).
    """
    indicators: dict[str, Any] = {}

    # 1) Режим: fail-CLOSED - работаем только в явном RANGING.
    regime = str(ctx.get("regime", "") or "").upper()
    if regime != "RANGING":
        return _veto(
            "mr_regime_not_ranging",
            f"Режим '{regime or 'UNKNOWN'}' - mean-reversion не применяется",
            indicators,
        )

    # 2) Blackout (макрорелиз, CPI и т.п.) - не торгуем.
    if bool(ctx.get("blackout", False)):
        return _veto(
            "mr_blackout",
            "Активен blackout перед макрорелизом",
            indicators,
        )

    # 3) Данные.
    c15 = ctx.get("candles_15m") or []
    # Для ADX(14) нужен минимум 2*period = 28; для BB(20) - 20;
    # для RSI(14) - 15. Возьмём с запасом - 40.
    if len(c15) < 40:
        return _veto(
            "mr_insufficient_data",
            "Недостаточно 15m-свечей",
            indicators,
        )

    highs, lows, closes = _extract(c15)
    if len(closes) < 40:
        return _veto(
            "mr_insufficient_data",
            "Недостаточно 15m-свечей после парсинга",
            indicators,
        )

    lower, middle, upper = bollinger_bands(closes, _BB_PERIOD, _BB_STD_MULT)
    rsi_series = rsi(closes, _RSI_PERIOD)
    atr_series = atr(highs, lows, closes, _ATR_PERIOD)
    adx_series = adx(highs, lows, closes, _ADX_PERIOD)

    close_15m = closes[-1]
    rsi_cur = rsi_series[-1] if rsi_series else None
    atr_15m = atr_series[-1] if atr_series else None
    adx_15m = adx_series[-1] if adx_series else None

    if None in (lower, middle, upper, rsi_cur, atr_15m, adx_15m):
        return _veto(
            "mr_insufficient_data",
            "Индикаторы 15m не рассчитались (мало данных)",
            indicators,
        )

    atr_pct = (atr_15m / close_15m) if close_15m > 0 else 0.0
    indicators = {
        "close_15m": close_15m,
        "bb_lower": lower,
        "bb_middle": middle,
        "bb_upper": upper,
        "rsi_15m": rsi_cur,
        "atr_15m": atr_15m,
        "atr_pct_15m": atr_pct,
        "adx_15m": adx_15m,
    }

    symbol = str(ctx.get("symbol") or "").upper()
    min_atr = _min_atr_pct_for(symbol)

    # 4) ADX: сильный тренд - не торгуем mean-reversion.
    if adx_15m >= _ADX_RANGE_MAX:
        return _veto(
            "mr_adx_trending",
            f"ADX(14) 15m = {adx_15m:.1f} >= {_ADX_RANGE_MAX:.0f}",
            indicators,
        )

    # 5) Волатильность: мёртвый рынок - пропускаем.
    if atr_pct < min_atr:
        return _veto(
            "mr_vol_low",
            f"ATR(15m) {atr_pct * 100:.3f}% ниже порога "
            f"{min_atr * 100:.3f}% для {symbol or 'symbol'}",
            indicators,
        )

    # 6) Определяем сторону по касанию полосы.
    if close_15m <= lower:
        # LONG кандидат: RSI должен быть перепродан.
        if rsi_cur >= _RSI_OVERSOLD:
            return _veto(
                "mr_rsi_neutral",
                f"RSI(14) = {rsi_cur:.1f} >= {_RSI_OVERSOLD:.0f} (нет перепроданности)",
                indicators,
            )
        entry = close_15m
        sl = entry - _ATR_STOP_MULT * atr_15m
        tp = middle
        return {
            "signal": "LONG",
            "reason": "Касание нижней BB + RSI<30 в боковике",
            "filter": None,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "qty": 0.0,
            "indicators": indicators,
        }

    if close_15m >= upper:
        # SHORT кандидат: RSI должен быть перекуплен.
        if rsi_cur <= _RSI_OVERBOUGHT:
            return _veto(
                "mr_rsi_neutral",
                f"RSI(14) = {rsi_cur:.1f} <= {_RSI_OVERBOUGHT:.0f} (нет перекупленности)",
                indicators,
            )
        entry = close_15m
        sl = entry + _ATR_STOP_MULT * atr_15m
        tp = middle
        return {
            "signal": "SHORT",
            "reason": "Касание верхней BB + RSI>70 в боковике",
            "filter": None,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "qty": 0.0,
            "indicators": indicators,
        }

    # Цена внутри полос - нет сетапа.
    return _veto(
        "mr_no_band_touch",
        f"close {close_15m:.4f} внутри BB [{lower:.4f}; {upper:.4f}]",
        indicators,
    )


# --- Размер позиции ----------------------------------------------------------

def position_size(
    equity: float,
    entry: float,
    hard_stop: float,
    *,
    risk_per_trade: float,
) -> float:
    """Простой R-сайзер: qty = (equity * R) / |entry - stop|.

    Мы не переиспользуем strategy_v2.position_size, так как та функция
    жёстко привязана к ATR_STOP_MULT * ATR(1h) внутри расчёта дистанции.
    Здесь стоп строится от ATR(15m) с другим множителем (1.5), поэтому
    локальный расчёт честнее и короче.
    """
    if equity <= 0 or entry <= 0:
        return 0.0
    price_distance = abs(float(entry) - float(hard_stop))
    if price_distance <= 0:
        return 0.0
    risk_amount = float(equity) * max(float(risk_per_trade), 0.0)
    if risk_amount <= 0:
        return 0.0
    qty = risk_amount / price_distance
    return max(qty, 0.0)


# --- Универсальный интерфейс для диспетчера и бэктестера ---------------------

def on_bar(ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Обёртка: evaluate_signal + position_size -> Order dict или None.

    Формат возвращаемого ордера идентичен strategy_v2.on_bar, чтобы
    диспетчер стратегий в main.py мог дергать любую подсистему без знания
    её внутренностей.
    """
    signal = evaluate_signal(ctx)
    if not signal.get("signal"):
        return None

    entry = float(signal.get("entry") or 0.0)
    sl = float(signal.get("sl") or 0.0)
    equity = float(ctx.get("equity") or 0.0)
    # В 2 раза меньше Donchian: ожидаем больше сделок и короче R.
    risk = float(getattr(config, "RISK_PER_TRADE", 0.01)) * 0.5

    qty = position_size(equity, entry, sl, risk_per_trade=risk)
    if qty <= 0:
        return None

    side = "Buy" if signal["signal"] == "LONG" else "Sell"
    indicators = signal.get("indicators") or {}
    return {
        "symbol": ctx.get("symbol"),
        "side": side,
        "qty": qty,
        "type": "limit",
        "limit_price": entry,
        "hard_stop": sl,
        "meta": {
            "reason": signal.get("reason", ""),
            "filter": signal.get("filter"),
            "strategy": STRATEGY_NAME,
            "tp": float(signal.get("tp") or 0.0),
            "indicators": indicators,
        },
    }


def on_fill(ctx: dict[str, Any], fill: dict[str, Any]) -> None:
    """Хук на исполнение ордера. В живом рантайме сопровождение ведёт
    движок main.py; для совместимости с бэктестером оставлен no-op."""
    return None


def set_params(**kwargs: Any) -> None:
    """Хук настройки гиперпараметров (для walkforward).

    На текущем этапе параметры захардкожены константами модуля;
    kwargs принимаются и молча игнорируются для совместимости интерфейса
    со strategy_v2.set_params.
    """
    return None
