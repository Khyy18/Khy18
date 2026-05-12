"""Стратегия v2 - Donchian-пробой с мультитаймфреймовым трендовым фильтром.

Правила входа (детерминированные, без ИИ-гейта):
  LONG  - дневной тренд выше EMA200, 4-часовой выше EMA50, часовой пробивает
          20-часовой максимум, ATR(1h) >= 0.3% от цены, нет blackout и не CRISIS.
  SHORT - дневной тренд ниже EMA200, 4-часовой ниже EMA50, часовой пробивает
          10-часовой минимум, ADX(1h) > 25, нет blackout и не CRISIS.

Риск:
  - Жёсткий стоп = вход -/+ ATR_STOP_MULT * ATR(1h), без исключений.
  - Трейлинг «канделяр» активируется после движения >= 1 * ATR в плюс
    и подтягивается за high/low water mark с коэффициентом ATR_TRAIL_MULT.
  - Таймстоп (TIME_STOP_HOURS) закрывает сделки, зависшие в нуле или минусе.

Vol-targeting сайзинг: последняя 30-дневная реализованная волатильность
масштабируется к TARGET_ANNUAL_VOL, результат ограничен [0.25, 4.0].

Все вычисления - чистый Python (statistics + math), без сторонних библиотек.
"""

from __future__ import annotations

import math
import statistics
from datetime import datetime
from typing import Any, Optional

import config
# ema переиспользуем из strategy_v1, чтобы индикаторы не расходились.
from strategy_v1 import ema  # noqa: F401


STRATEGY_NAME = "strategy_v2"
SUPPORTED_TIMEFRAMES = ("1h", "4h", "1d")

# Закрытый набор ASCII-тегов вето для Telegram-кнопки «ПОЧЕМУ МИМО?».
_FILTER_TAGS = (
    "trend_1d",
    "trend_4h",
    "breakout",
    "vol_low",
    "vol_confirm_weak",
    "blackout",
    "regime_crisis",
    "adx_weak",
    "insufficient_data",
)


# --- Индикаторы (чистый Python) ---

def atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[Optional[float]]:
    """Average True Range по методу Уайлдера (идентично strategy_v1.atr)."""
    n = len(closes)
    out: list[Optional[float]] = [None] * n
    if period <= 0 or n < period + 1 or not (len(highs) == len(lows) == n):
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


def adx(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[Optional[float]]:
    """Wilder ADX с раздельным сглаживанием +DM / -DM / TR и последующим DX -> ADX.

    Возвращает список длины n. До накопления значений стоят None.
    Требует n >= 2 * period, чтобы появился хотя бы один валидный ADX.
    """
    n = len(closes)
    out: list[Optional[float]] = [None] * n
    if period <= 0 or n < 2 * period or not (len(highs) == len(lows) == n):
        return out

    dm_plus = [0.0] * n
    dm_minus = [0.0] * n
    tr = [0.0] * n
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        dm_plus[i] = up if (up > dn and up > 0) else 0.0
        dm_minus[i] = dn if (dn > up and dn > 0) else 0.0
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    # Сглаживание по Уайлдеру (суммы): первая сумма - по первым period значениям,
    # далее sum_next = sum_prev - sum_prev/period + new_value.
    s_dm_plus = sum(dm_plus[1 : period + 1])
    s_dm_minus = sum(dm_minus[1 : period + 1])
    s_tr = sum(tr[1 : period + 1])

    dx_series: list[Optional[float]] = [None] * n
    for i in range(period, n):
        if i > period:
            s_dm_plus = s_dm_plus - s_dm_plus / period + dm_plus[i]
            s_dm_minus = s_dm_minus - s_dm_minus / period + dm_minus[i]
            s_tr = s_tr - s_tr / period + tr[i]
        if s_tr <= 0:
            dx_series[i] = 0.0
            continue
        plus_di = 100.0 * s_dm_plus / s_tr
        minus_di = 100.0 * s_dm_minus / s_tr
        denom = plus_di + minus_di
        dx = 100.0 * abs(plus_di - minus_di) / denom if denom > 0 else 0.0
        dx_series[i] = dx

    # Сглаживаем DX в ADX (тоже по Уайлдеру).
    first_idx = 2 * period - 1
    if first_idx >= n:
        return out
    window = [v for v in dx_series[period : first_idx + 1] if v is not None]
    if len(window) < period:
        return out
    first_adx = sum(window) / period
    out[first_idx] = first_adx
    prev = first_adx
    for i in range(first_idx + 1, n):
        dx_val = dx_series[i]
        if dx_val is None:
            continue
        prev = (prev * (period - 1) + dx_val) / period
        out[i] = prev
    return out


def highest(values: list[float], n: int) -> Optional[float]:
    """Максимум последних n элементов (или None, если данных меньше)."""
    if n <= 0 or len(values) < n:
        return None
    try:
        return max(values[-n:])
    except (TypeError, ValueError):
        return None


def lowest(values: list[float], n: int) -> Optional[float]:
    """Минимум последних n элементов (или None, если данных меньше)."""
    if n <= 0 or len(values) < n:
        return None
    try:
        return min(values[-n:])
    except (TypeError, ValueError):
        return None


# --- Внутренние помощники ---

def _extract(candles: list[dict[str, Any]]) -> tuple[list[float], list[float], list[float]]:
    """Из списка свечей {ts,open,high,low,close,volume} вернуть (highs,lows,closes)."""
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
        "filter": tag if tag in _FILTER_TAGS else "insufficient_data",
        "entry": 0.0,
        "sl": 0.0,
        "qty": 0.0,
        "indicators": indicators or {},
    }


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _check_volume_confirmation(
    c1h: list[dict[str, Any]],
    indicators: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Volume-confirmation фильтр Donchian-пробоев.

    Идея: пробой на аномально низком объёме - кандидат на fakeout. Считаем
    SMA(20) по объёмам ПРЕДЫДУЩИХ 20 свечей (текущая не входит в среднее,
    иначе её же объём влияет на порог) и сравниваем с объёмом пробойной
    свечи.

    Возвращает dict вето, если подтверждения нет. Возвращает None, если
    фильтр пройден ИЛИ данных для проверки недостаточно (graceful fallback:
    отсутствие объёмов не должно блокировать торговлю).

    Обогащает indicators ключами volume_current / volume_sma20 / volume_ratio
    для последующего логирования.
    """
    # Требуется минимум 21 свеча: 20 в SMA + текущая.
    if not c1h or len(c1h) < 21:
        return None

    # Извлекаем объёмы; колонка может отсутствовать на некоторых источниках -
    # тогда skip, а не veto.
    try:
        volumes = [float(c["volume"]) for c in c1h[-21:]]
    except (KeyError, TypeError, ValueError):
        return None

    volume_current = volumes[-1]
    prev20 = volumes[:-1]
    volume_sma20 = sum(prev20) / len(prev20) if prev20 else 0.0

    # Guard против деления на ноль и NaN (NaN != NaN).
    if (
        volume_sma20 is None
        or volume_sma20 != volume_sma20
        or volume_sma20 <= 0
    ):
        return None

    volume_ratio = volume_current / volume_sma20
    indicators["volume_current"] = volume_current
    indicators["volume_sma20"] = volume_sma20
    indicators["volume_ratio"] = volume_ratio

    mult = float(getattr(config, "VOLUME_CONFIRMATION_MULT", 1.0) or 1.0)
    threshold = volume_sma20 * mult
    if volume_current < threshold:
        return _veto(
            "vol_confirm_weak",
            f"vol={volume_current:.0f} < sma20*{mult:.2f}={threshold:.0f}",
            indicators,
        )
    return None


# --- Публичная логика сигнала ---

def evaluate_signal(ctx: dict[str, Any]) -> dict[str, Any]:
    """Оценить последний закрытый бар и вернуть сигнал LONG/SHORT или вето.

    Формат ctx:
      {
        'symbol': str,
        'candles_1h': list[dict],
        'candles_4h': list[dict],
        'candles_1d': list[dict],
        'equity': float,
        'atr_1h_now': float,     # опционально, используется верхним слоем
        'blackout': bool,
        'regime': str            # 'TRENDING'|'RANGING'|'CRISIS'
      }
    Все candles_* содержат последние ЗАКРЫТЫЕ свечи (форм. бар отброшен).
    """
    c1h = ctx.get("candles_1h") or []
    c4h = ctx.get("candles_4h") or []
    c1d = ctx.get("candles_1d") or []

    # 1) Недостаточно данных.
    if len(c1d) < 200 or len(c4h) < 50 or len(c1h) < 30:
        return _veto("insufficient_data", "Недостаточно свечей")

    h1h, l1h, cl1h = _extract(c1h)
    _, _, cl4h = _extract(c4h)
    _, _, cl1d = _extract(c1d)
    if len(cl1d) < 200 or len(cl4h) < 50 or len(cl1h) < 30:
        return _veto("insufficient_data", "Недостаточно свечей после парсинга")

    ema200_1d_series = ema(cl1d, 200)
    ema50_4h_series = ema(cl4h, 50)
    atr_1h_series = atr(h1h, l1h, cl1h, 14)
    adx_1h_series = adx(h1h, l1h, cl1h, 14)

    ema200_1d = ema200_1d_series[-1]
    ema50_4h = ema50_4h_series[-1]
    atr_1h = atr_1h_series[-1]
    adx_1h = adx_1h_series[-1]
    close_1d = cl1d[-1]
    close_4h = cl4h[-1]
    close_1h = cl1h[-1]

    if None in (ema200_1d, ema50_4h, atr_1h, adx_1h):
        return _veto(
            "insufficient_data",
            "Недостаточно свечей для расчёта индикаторов",
        )

    donchian_hi = highest(h1h[:-1], config.DONCHIAN_LONG_LOOKBACK)
    donchian_lo = lowest(l1h[:-1], config.DONCHIAN_SHORT_LOOKBACK)
    atr_pct = (atr_1h / close_1h) if close_1h > 0 else 0.0

    indicators: dict[str, Any] = {
        "close_1h": close_1h,
        "ema200_1d": ema200_1d,
        "ema50_4h": ema50_4h,
        "donchian_hi": donchian_hi,
        "donchian_lo": donchian_lo,
        "atr_1h": atr_1h,
        "atr_pct": atr_pct,
        "adx_1h": adx_1h,
    }

    # 2) Blackout (приоритет выше режимного гейта - макро-события переводят
    # всё в «не торгуем»).
    if bool(ctx.get("blackout", False)):
        return _veto(
            "blackout",
            "Активен blackout перед макрорелизом",
            indicators,
        )

    # 3) Режим (CRISIS - не торгуем).
    regime = str(ctx.get("regime", "") or "").upper()
    if regime == "CRISIS":
        return _veto("regime_crisis", "Режим CRISIS по символу", indicators)

    # 4) Сторона по дневному тренду.
    if close_1d > ema200_1d:
        # LONG кандидат: 4h-тренд, пробой, волатильность.
        if close_4h <= ema50_4h:
            return _veto(
                "trend_4h",
                "4-часовой тренд ниже EMA50",
                indicators,
            )
        if donchian_hi is None or close_1h <= donchian_hi:
            return _veto(
                "breakout",
                "Нет пробоя 20-часового хая",
                indicators,
            )
        veto = _check_volume_confirmation(c1h, indicators)
        if veto is not None:
            return veto
        # Per-symbol минимум ATR: SOL/ETH/BTC имеют разную базовую
        # волатильность, единый порог 0.3% отсекает либо мало, либо
        # много. Берём из config.MIN_ATR_PCT[symbol], fallback на
        # MIN_ATR_PCT_DEFAULT. Символ читаем из ctx (не обязательно
        # присутствует - устойчиво к отсутствию).
        symbol = str(ctx.get("symbol") or "").upper()
        min_atr_map = getattr(config, "MIN_ATR_PCT", {}) or {}
        min_atr_default = float(
            getattr(config, "MIN_ATR_PCT_DEFAULT", 0.003) or 0.003
        )
        min_atr = float(min_atr_map.get(symbol, min_atr_default))
        if atr_pct < min_atr:
            return _veto(
                "vol_low",
                f"ATR {atr_pct * 100:.3f}% ниже порога {min_atr * 100:.3f}% для {symbol or 'symbol'}",
                indicators,
            )
        entry = close_1h
        sl = compute_hard_stop(entry, atr_1h, "LONG")
        return {
            "signal": "LONG",
            "reason": "Пробой 20-часового хая при растущем тренде",
            "filter": None,
            "entry": entry,
            "sl": sl,
            "qty": 0.0,
            "indicators": indicators,
        }

    if close_1d < ema200_1d:
        # SHORT кандидат: 4h-тренд, пробой, ADX.
        if close_4h >= ema50_4h:
            return _veto(
                "trend_4h",
                "4-часовой тренд выше EMA50",
                indicators,
            )
        if donchian_lo is None or close_1h >= donchian_lo:
            return _veto(
                "breakout",
                "Нет пробоя 10-часового лоя",
                indicators,
            )
        veto = _check_volume_confirmation(c1h, indicators)
        if veto is not None:
            return veto
        if adx_1h <= 25:
            return _veto("adx_weak", "ADX(14) ниже 25", indicators)
        entry = close_1h
        sl = compute_hard_stop(entry, atr_1h, "SHORT")
        return {
            "signal": "SHORT",
            "reason": "Пробой 10-часового лоя при нисходящем тренде",
            "filter": None,
            "entry": entry,
            "sl": sl,
            "qty": 0.0,
            "indicators": indicators,
        }

    # close_1d == ema200_1d (крайне редкий случай): нет чёткого тренда.
    return _veto(
        "trend_1d",
        "Дневной тренд совпадает с EMA200",
        indicators,
    )


# --- Риск и размер позиции ---

def position_size(
    equity: float,
    close_1d_series: list[float],
    atr_1h: float,
    *,
    risk_per_trade: float = config.RISK_PER_TRADE,
    target_annual_vol: float = config.TARGET_ANNUAL_VOL,
) -> float:
    """Расчёт количества контрактов через vol-targeting + ATR-стоп.

    realized_vol - годовая волатильность дневных лог-/арифм-доходностей
    (используем простую арифметическую доходность r = p_i/p_{i-1} - 1).
    vol_scalar = clamp(target_annual_vol / realized_vol, 0.25, 4.0).
    При нехватке данных (<31 дневной свечи) vol_scalar = 1.0.
    """
    if equity <= 0 or atr_1h is None or atr_1h <= 0:
        return 0.0

    vol_scalar = 1.0
    try:
        closes = [float(c) for c in (close_1d_series or [])]
    except (TypeError, ValueError):
        closes = []

    if len(closes) >= 31:
        returns: list[float] = []
        for i in range(len(closes) - 30, len(closes)):
            prev = closes[i - 1]
            cur = closes[i]
            if prev > 0:
                returns.append((cur - prev) / prev)
        if len(returns) >= 2:
            try:
                realized_vol = statistics.stdev(returns) * math.sqrt(365.0)
            except statistics.StatisticsError:
                realized_vol = 0.0
            realized_vol = max(realized_vol, 0.01)
            vol_scalar = _clamp(
                target_annual_vol / realized_vol, 0.25, 4.0
            )

    risk_amount = equity * max(float(risk_per_trade), 0.0) * vol_scalar
    stop_distance = float(config.ATR_STOP_MULT) * float(atr_1h)
    if stop_distance <= 0:
        return 0.0
    qty = risk_amount / stop_distance
    return max(qty, 0.0)


def compute_hard_stop(entry: float, atr_at_entry: float, side: str) -> float:
    """Жёсткий стоп = вход -/+ ATR_STOP_MULT * ATR. Защита от нулевого ATR."""
    if entry <= 0 or atr_at_entry is None or atr_at_entry <= 0:
        return float(entry)
    distance = float(config.ATR_STOP_MULT) * float(atr_at_entry)
    s = (side or "").strip().upper()
    if s in ("LONG", "BUY"):
        return float(entry) - distance
    if s in ("SHORT", "SELL"):
        return float(entry) + distance
    return float(entry)


def compute_chandelier(
    high_since_entry: float,
    low_since_entry: float,
    atr_now: float,
    side: str,
    entry: float,
    *,
    activation_atr: float,
    trail_mult: float = config.ATR_TRAIL_MULT,
) -> Optional[float]:
    """Chandelier-трейлинг. Активируется после движения >= 1 * activation_atr
    в сторону сделки. Возвращает уровень стопа или None (пока не активирован)."""
    if entry <= 0 or atr_now is None or atr_now <= 0:
        return None
    if activation_atr is None or activation_atr <= 0:
        return None

    s = (side or "").strip().upper()
    if s in ("LONG", "BUY"):
        if high_since_entry - entry < activation_atr:
            return None
        return float(high_since_entry) - float(trail_mult) * float(atr_now)
    if s in ("SHORT", "SELL"):
        if entry - low_since_entry < activation_atr:
            return None
        return float(low_since_entry) + float(trail_mult) * float(atr_now)
    return None


def should_time_stop(
    entry_ts_iso: str,
    now_iso: str,
    side: str,
    entry: float,
    current_price: float,
    *,
    hours: float = config.TIME_STOP_HOURS,
) -> bool:
    """True, если с момента входа прошло >= hours часов И PnL не положительный."""
    try:
        t0 = datetime.fromisoformat(str(entry_ts_iso))
        t1 = datetime.fromisoformat(str(now_iso))
    except (TypeError, ValueError):
        return False
    try:
        elapsed = (t1 - t0).total_seconds()
    except TypeError:
        # naive vs aware - считаем, что не можем сравнить.
        return False
    if elapsed < float(hours) * 3600.0:
        return False
    s = (side or "").strip().upper()
    if s in ("LONG", "BUY"):
        return current_price <= entry
    if s in ("SHORT", "SELL"):
        return current_price >= entry
    return False


# --- Универсальный интерфейс для бэктестера и лайв-рантайма ---

def on_bar(ctx: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Тонкая обёртка: evaluate_signal + position_size -> Order dict или None."""
    signal = evaluate_signal(ctx)
    if not signal.get("signal"):
        return None

    indicators = signal.get("indicators") or {}
    atr_1h = float(indicators.get("atr_1h") or 0.0)
    c1d = ctx.get("candles_1d") or []
    try:
        close_1d_series = [float(c["close"]) for c in c1d]
    except (KeyError, TypeError, ValueError):
        close_1d_series = []

    equity = float(ctx.get("equity") or 0.0)
    qty = position_size(equity, close_1d_series, atr_1h)
    if qty <= 0:
        return None

    side = "Buy" if signal["signal"] == "LONG" else "Sell"
    return {
        "symbol": ctx.get("symbol"),
        "side": side,
        "qty": qty,
        "type": "limit",
        "limit_price": float(signal["entry"]),
        "hard_stop": float(signal["sl"]),
        "meta": {
            "reason": signal.get("reason", ""),
            "filter": signal.get("filter"),
            "indicators": indicators,
        },
    }


def on_fill(ctx: dict[str, Any], fill: dict[str, Any]) -> None:
    """Хук на исполнение ордера. В v2 сделки ведёт движок, здесь no-op."""
    return None


def set_params(**kwargs: Any) -> None:
    """Хук настройки гиперпараметров стратегии (для walkforward).

    В v2 на этапе FEAT-002 никаких настраиваемых параметров ещё нет,
    поэтому аргументы молча игнорируются. Сюда позже можно будет пробросить
    длины Donchian, множители ATR, пороги ADX и т.п.
    """
    return None
