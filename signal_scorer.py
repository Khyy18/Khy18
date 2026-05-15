"""AI Signal Scorer: оценка качества momentum-сигнала (0..1).

Скорирует сигнал EMA cross по набору фич:
  - EMA separation: |fast - slow| / price (сила расхождения)
  - Volume spike: current_volume / avg_volume_20 (подтверждение объёмом)
  - RSI position: фильтрует перекупленность/перепроданность
  - Candle body ratio: body / range (полнотелые = сильные)

Score = weighted sum, нормализованный в [0, 1].
Веса калибруются бэктестом, дефолты подобраны эмпирически.

Использование:
  score = compute_signal_score(klines, fast_ema, slow_ema, signal)
  if score < MOMENTUM_MIN_SIGNAL_SCORE:
      skip entry

Kelly sizing:
  position_size = base_size * kelly_fraction(score, winrate, avg_win, avg_loss)
"""

from __future__ import annotations

from typing import Any


# ─── RSI (stdlib) ──────────────────────────────────────────────────────

def calc_rsi(closes: list[float], period: int = 14) -> float:
    """Relative Strength Index (0-100). 0 при недостатке данных."""
    if len(closes) < period + 1:
        return 50.0  # нейтральный fallback

    gains: list[float] = []
    losses: list[float] = []

    for i in range(len(closes) - period, len(closes)):
        delta = closes[i] - closes[i - 1]
        if delta > 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(delta))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


# ─── Фичи ─────────────────────────────────────────────────────────────

def _ema_separation(fast_ema: list[float], slow_ema: list[float], price: float) -> float:
    """Нормализованное расхождение EMA. Чем больше — тем сильнее сигнал."""
    if not fast_ema or not slow_ema or price <= 0:
        return 0.0
    return abs(fast_ema[-1] - slow_ema[-1]) / price


def _volume_spike(klines: list[dict[str, Any]], period: int = 20) -> float:
    """Текущий volume / avg. >1 = выше среднего."""
    if len(klines) < period + 1:
        return 1.0
    volumes = [float(k.get("volume", 0)) for k in klines]
    current = volumes[-1]
    avg = sum(volumes[-period - 1:-1]) / period
    if avg == 0:
        return 1.0
    return current / avg


def _candle_body_ratio(klines: list[dict[str, Any]]) -> float:
    """Body / Range последней свечи. 1.0 = полнотелая, 0.0 = дожи."""
    if not klines:
        return 0.5
    k = klines[-1]
    high = float(k["high"])
    low = float(k["low"])
    open_p = float(k["open"])
    close_p = float(k["close"])
    range_val = high - low
    if range_val == 0:
        return 0.0
    body = abs(close_p - open_p)
    return body / range_val


def _rsi_filter(rsi: float, signal: str) -> float:
    """RSI-фильтр: штрафует вход в перекупленную/перепроданную зону.

    LONG при RSI > 70 → плохо (0.3). LONG при RSI 40-60 → хорошо (1.0).
    SHORT при RSI < 30 → плохо (0.3). SHORT при RSI 40-60 → хорошо (1.0).
    """
    if signal == "LONG":
        if rsi > 75:
            return 0.2
        elif rsi > 65:
            return 0.5
        elif rsi < 30:
            return 1.0  # Oversold → хороший вход для LONG
        else:
            return 0.8
    else:  # SHORT
        if rsi < 25:
            return 0.2
        elif rsi < 35:
            return 0.5
        elif rsi > 70:
            return 1.0  # Overbought → хороший вход для SHORT
        else:
            return 0.8


# ─── Scorer ────────────────────────────────────────────────────────────

def compute_signal_score(
    klines: list[dict[str, Any]],
    fast_ema: list[float],
    slow_ema: list[float],
    signal: str,
    w_ema_sep: float = 0.30,
    w_volume: float = 0.25,
    w_rsi: float = 0.25,
    w_body: float = 0.20,
) -> float:
    """Вычислить score сигнала (0.0 .. 1.0).

    Чем выше — тем увереннее сигнал, тем больший размер позиции.

    Args:
        klines: свечи (минимум 21 штука)
        fast_ema: быстрая EMA
        slow_ema: медленная EMA
        signal: "LONG" или "SHORT"
        w_*: веса фич (сумма = 1.0)

    Returns:
        float 0.0 .. 1.0
    """
    if not klines:
        return 0.0

    closes = [float(k["close"]) for k in klines]
    price = closes[-1] if closes else 0.0

    # Фичи (каждая нормализована в 0..1 или около того)
    ema_sep = _ema_separation(fast_ema, slow_ema, price)
    # Нормализуем: 0.5% separation = 1.0, 0% = 0.0
    ema_score = min(1.0, ema_sep / 0.005)

    vol_spike = _volume_spike(klines)
    # Нормализуем: ratio 2.0 = 1.0, ratio 1.0 = 0.5
    vol_score = min(1.0, vol_spike / 2.0)

    rsi = calc_rsi(closes, period=14)
    rsi_score = _rsi_filter(rsi, signal)

    body_score = _candle_body_ratio(klines)

    # Взвешенная сумма
    raw_score = (
        w_ema_sep * ema_score
        + w_volume * vol_score
        + w_rsi * rsi_score
        + w_body * body_score
    )

    # Clamp [0, 1]
    return max(0.0, min(1.0, raw_score))


# ─── Kelly Position Sizing ─────────────────────────────────────────────

def kelly_fraction(
    signal_score: float,
    winrate: float = 0.45,
    avg_win: float = 0.04,
    avg_loss: float = 0.02,
    max_fraction: float = 0.5,
) -> float:
    """Модифицированный Kelly criterion с учётом signal score.

    Returns:
        Множитель размера позиции (0.1 .. max_fraction).
        Никогда не возвращает 0 — минимум 0.1 (10% от базового размера).
    """
    if avg_win <= 0 or winrate <= 0:
        return 0.1

    # Классический Kelly
    kelly = (winrate * avg_win - (1 - winrate) * avg_loss) / avg_win

    # Масштабируем confidence-ом сигнала
    adjusted = kelly * signal_score

    # Half-Kelly для безопасности
    half_kelly = adjusted * 0.5

    # Clamp
    return max(0.1, min(max_fraction, half_kelly))




# ─── Volume Anomaly Early Exit ─────────────────────────────────────────

def detect_volume_anomaly_exit(
    klines: list[dict[str, Any]],
    position_side: str,
    z_threshold: float = 2.5,
    lookback: int = 20,
) -> bool:
    """Определить, нужно ли выходить досрочно из-за аномалии volume.

    Если volume > z_threshold σ от среднего И направление последних 3 баров
    противоположно позиции — early exit (институционалы выходят).

    Args:
        klines: свечи (минимум lookback + 3 штуки)
        position_side: "LONG" или "SHORT"
        z_threshold: порог z-score для volume (default 2.5σ)
        lookback: окно для расчёта среднего volume

    Returns:
        True если нужно закрыть позицию досрочно.
    """
    if len(klines) < lookback + 3:
        return False

    # Средний и std volume за lookback
    volumes = [float(k.get("volume", 0)) for k in klines[-lookback - 1:-1]]
    current_vol = float(klines[-1].get("volume", 0))

    if not volumes:
        return False

    avg_vol = sum(volumes) / len(volumes)
    if avg_vol == 0:
        return False

    variance = sum((v - avg_vol) ** 2 for v in volumes) / len(volumes)
    std_vol = variance ** 0.5
    if std_vol == 0:
        return False

    z_score = (current_vol - avg_vol) / std_vol

    if z_score < z_threshold:
        return False  # Volume не аномальный

    # Проверяем направление последних 3 баров
    last_3_closes = [float(klines[i]["close"]) for i in range(-3, 0)]
    if len(last_3_closes) < 3:
        return False

    price_direction = last_3_closes[-1] - last_3_closes[0]

    # Если LONG и цена падает при высоком volume → early exit
    if position_side == "LONG" and price_direction < 0:
        return True
    # Если SHORT и цена растёт при высоком volume → early exit
    if position_side == "SHORT" and price_direction > 0:
        return True

    return False
