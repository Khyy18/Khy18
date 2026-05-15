"""Конфигурация КОМБО-бота (funding + grid + momentum).

Расширяет config.py дополнительными параметрами для grid и momentum
стратегий. Глобальные параметры (Telegram, биржи) берутся из config.py.
"""

from __future__ import annotations

import os

import config  # noqa: F401 — base config, все ключи доступны через config.*


# ─── Аллокация капитала ───────────────────────────────────────────────
# Доли от общего equity. Сумма должна быть <= 1.0.
ALLOC_FUNDING_PCT = float(os.getenv("ALLOC_FUNDING_PCT", "0.50") or 0.50)
ALLOC_GRID_PCT = float(os.getenv("ALLOC_GRID_PCT", "0.30") or 0.30)
ALLOC_MOMENTUM_PCT = float(os.getenv("ALLOC_MOMENTUM_PCT", "0.20") or 0.20)

# Стартовый капитал (USDT). Если 0 — берётся из суммы балансов на биржах.
TOTAL_CAPITAL_USDT = float(os.getenv("TOTAL_CAPITAL_USDT", "550") or 550)


# ─── Глобальный kill-switch ───────────────────────────────────────────
# Если суммарный drawdown по ВСЕМ стратегиям > порога — ВСЕ стратегии
# останавливаются. Снимается только вручную через Telegram.
GLOBAL_MAX_DRAWDOWN_PCT = float(os.getenv("GLOBAL_MAX_DRAWDOWN_PCT", "0.15") or 0.15)


# ─── Grid-бот ─────────────────────────────────────────────────────────
# Символы для grid-торговли.
GRID_SYMBOLS: list[str] = [
    s.strip() for s in os.getenv("GRID_SYMBOLS", "BTCUSDT,ETHUSDT").split(",") if s.strip()
]

# Биржа для grid (одна). По умолчанию bybit.
GRID_EXCHANGE = os.getenv("GRID_EXCHANGE", "bybit").strip().lower()

# Количество уровней сетки (buy + sell ордера).
GRID_LEVELS = int(os.getenv("GRID_LEVELS", "10") or 10)

# Шаг сетки в процентах от текущей цены.
# 0.003 = 0.3% между уровнями. При 10 уровнях покрываем ±1.5%.
GRID_STEP_PCT = float(os.getenv("GRID_STEP_PCT", "0.003") or 0.003)

# Размер одного ордера в USDT (notional). Рассчитывается автоматически
# из аллокации, но можно задать вручную.
GRID_ORDER_USDT = float(os.getenv("GRID_ORDER_USDT", "0") or 0)

# Плечо для grid. Spot-like = 1, perp с плечом = 2-5.
GRID_LEVERAGE = int(os.getenv("GRID_LEVERAGE", "1") or 1)

# Период пересчёта сетки (секунды). Если цена ушла за пределы сетки —
# пересоздаём ордера.
GRID_REBALANCE_INTERVAL_SEC = float(os.getenv("GRID_REBALANCE_INTERVAL_SEC", "300") or 300)

# Включен ли grid-модуль.
GRID_ENABLED = os.getenv("GRID_ENABLED", "true").strip().lower() in (
    "1", "true", "yes", "on",
)


# ─── Momentum-стратегия ───────────────────────────────────────────────
# Символы для momentum.
MOMENTUM_SYMBOLS: list[str] = [
    s.strip() for s in os.getenv("MOMENTUM_SYMBOLS", "BTCUSDT,ETHUSDT").split(",") if s.strip()
]

# Биржа для momentum.
MOMENTUM_EXCHANGE = os.getenv("MOMENTUM_EXCHANGE", "bybit").strip().lower()

# EMA параметры.
MOMENTUM_EMA_FAST = int(os.getenv("MOMENTUM_EMA_FAST", "9") or 9)
MOMENTUM_EMA_SLOW = int(os.getenv("MOMENTUM_EMA_SLOW", "21") or 21)

# Плечо.
MOMENTUM_LEVERAGE = int(os.getenv("MOMENTUM_LEVERAGE", "3") or 3)

# Таймфрейм для свечей.
MOMENTUM_TIMEFRAME = os.getenv("MOMENTUM_TIMEFRAME", "15").strip()  # минуты

# Стоп-лосс в процентах от входа.
# 2.5% — оптимально для BTC 15m (не выбивает на шуме, ниже ATR*3)
MOMENTUM_STOP_LOSS_PCT = float(os.getenv("MOMENTUM_STOP_LOSS_PCT", "0.025") or 0.025)

# Тейк-профит в процентах от входа.
# 0 = без TP, прибыль фиксируется trailing stop (позволяет тренду бежать)
MOMENTUM_TAKE_PROFIT_PCT = float(os.getenv("MOMENTUM_TAKE_PROFIT_PCT", "0.0") or 0.0)

# Период проверки сигналов (секунды).
MOMENTUM_TICK_INTERVAL_SEC = float(os.getenv("MOMENTUM_TICK_INTERVAL_SEC", "60") or 60)

# Максимум одновременных позиций по momentum.
MOMENTUM_MAX_POSITIONS = int(os.getenv("MOMENTUM_MAX_POSITIONS", "2") or 2)

# Включена ли momentum-стратегия.
MOMENTUM_ENABLED = os.getenv("MOMENTUM_ENABLED", "true").strip().lower() in (
    "1", "true", "yes", "on",
)

# Минимальная волатильность (ATR/price) для входа. Фильтрует боковик.
# 0.4% ATR от цены — если меньше, не входим (слишком спокойно).
MOMENTUM_MIN_ATR_PCT = float(os.getenv("MOMENTUM_MIN_ATR_PCT", "0.004") or 0.004)

# Trailing stop: после достижения TRAIL_ACTIVATE_PCT прибыли — SL
# подтягивается на расстоянии TRAIL_DISTANCE_PCT от текущей цены.
# 0 = trailing отключён.
# 1.2% — агрессивный trailing для быстрой фиксации
MOMENTUM_TRAIL_ACTIVATE_PCT = float(os.getenv("MOMENTUM_TRAIL_ACTIVATE_PCT", "0.012") or 0.012)
# 0.8% — расстояние от цены до trailing SL
MOMENTUM_TRAIL_DISTANCE_PCT = float(os.getenv("MOMENTUM_TRAIL_DISTANCE_PCT", "0.008") or 0.008)


# ─── Grid: защита от unrealized loss ───────────────────────────────────
# Если суммарный unrealized loss по grid (все filled buy без matched sell)
# превышает этот % от equity → force close all grid + rebuild.
GRID_MAX_UNREALIZED_LOSS_PCT = float(os.getenv("GRID_MAX_UNREALIZED_LOSS_PCT", "0.05") or 0.05)

# ─── Spread guard ─────────────────────────────────────────────────────
# Если spread (ask - bid) / mid > порога → не размещать ордера (ликвидность
# испарилась, maintenance, flash crash). 0.005 = 0.5%.
MAX_SPREAD_PCT = float(os.getenv("MAX_SPREAD_PCT", "0.005") or 0.005)

# ─── Correlation guard ─────────────────────────────────────────────────
# Максимальное суммарное количество OPEN позиций momentum по коррелированным
# символам (BTC+ETH считаются одной группой). 0 = выключено.
CORRELATION_MAX_SAME_DIRECTION = int(os.getenv("CORRELATION_MAX_SAME_DIRECTION", "1") or 1)

# Группы коррелированных символов (одна группа = одно направление макс.)
CORRELATION_GROUPS: list[list[str]] = [
    ["BTCUSDT", "ETHUSDT"],
]

# ─── Performance monitoring ────────────────────────────────────────────
# Rolling window (количество сделок) для расчёта winrate.
PERF_ROLLING_WINDOW = int(os.getenv("PERF_ROLLING_WINDOW", "20") or 20)
# Минимальный допустимый winrate. Если rolling winrate < порога → alert.
PERF_MIN_WINRATE = float(os.getenv("PERF_MIN_WINRATE", "0.30") or 0.30)
# Cooldown между алертами о деградации (секунды).
PERF_ALERT_COOLDOWN_SEC = float(os.getenv("PERF_ALERT_COOLDOWN_SEC", "21600") or 21600)

# ─── Grid: адаптивный шаг ──────────────────────────────────────────────
# Динамический шаг = ATR(14) * GRID_ATR_MULTIPLIER. Если 0 — фиксированный GRID_STEP_PCT.
GRID_ATR_MULTIPLIER = float(os.getenv("GRID_ATR_MULTIPLIER", "1.5") or 1.5)

# Asymmetric grid: bias по тренду. Если цена > EMA50(4h) → больше sell-уровней.
# GRID_TREND_BIAS_LEVELS: на сколько уровней сдвигать (0 = симметрично).
GRID_TREND_BIAS_LEVELS = int(os.getenv("GRID_TREND_BIAS_LEVELS", "2") or 2)


# ─── Momentum: confirmation bar ───────────────────────────────────────
# Если True — вход не на свече кросса, а на следующей (если цена всё ещё
# подтверждает направление).
# false — тесты показывают +4.5% без vs -1.4% с confirmation
MOMENTUM_CONFIRMATION_BAR = os.getenv("MOMENTUM_CONFIRMATION_BAR", "false").strip().lower() in (
    "1", "true", "yes", "on",
)


# ─── Momentum: адаптивные стопы и фильтры ─────────────────────────────
# ATR-based SL/TP: если True — SL и TP рассчитываются из ATR * multiplier.
MOMENTUM_USE_ATR_STOPS = os.getenv("MOMENTUM_USE_ATR_STOPS", "true").strip().lower() in ("1", "true", "yes", "on")
MOMENTUM_ATR_SL_MULT = float(os.getenv("MOMENTUM_ATR_SL_MULT", "2.0") or 2.0)
MOMENTUM_ATR_TP_MULT = float(os.getenv("MOMENTUM_ATR_TP_MULT", "3.0") or 3.0)

# Минимальный ADX для входа (нет тренда = нет входа).
MOMENTUM_MIN_ADX = float(os.getenv("MOMENTUM_MIN_ADX", "20.0") or 20.0)

# RSI фильтр: не входить в LONG если RSI > overbought, не SHORT если RSI < oversold.
MOMENTUM_RSI_OVERBOUGHT = float(os.getenv("MOMENTUM_RSI_OVERBOUGHT", "70.0") or 70.0)
MOMENTUM_RSI_OVERSOLD = float(os.getenv("MOMENTUM_RSI_OVERSOLD", "30.0") or 30.0)


# ─── Риск-менеджмент ──────────────────────────────────────────────────
# Per-strategy daily loss limit (доля от equity). 0 = выключено.
# Если стратегия потеряла больше лимита за UTC-сутки — пауза до завтра.
RISK_DAILY_LOSS_GRID_PCT = float(os.getenv("RISK_DAILY_LOSS_GRID_PCT", "0.02") or 0.02)
RISK_DAILY_LOSS_MOMENTUM_PCT = float(os.getenv("RISK_DAILY_LOSS_MOMENTUM_PCT", "0.03") or 0.03)

# Max exposure per symbol: суммарная нетто-позиция по одному символу
# не должна превышать этот процент от equity (все стратегии вместе).
RISK_MAX_EXPOSURE_PER_SYMBOL_PCT = float(
    os.getenv("RISK_MAX_EXPOSURE_PER_SYMBOL_PCT", "0.30") or 0.30
)

# Heartbeat: если бот не отправлял heartbeat в Telegram дольше этого
# интервала (сек) — считается down. Внешний watchdog может мониторить.
HEARTBEAT_INTERVAL_SEC = float(os.getenv("COMBO_HEARTBEAT_INTERVAL_SEC", "600") or 600)


# --- Macro Calendar ---
MACRO_BLACKOUT_BEFORE_MIN = int(os.getenv("MACRO_BLACKOUT_BEFORE_MIN", "30") or 30)
MACRO_BLACKOUT_AFTER_MIN = int(os.getenv("MACRO_BLACKOUT_AFTER_MIN", "60") or 60)
MACRO_CALENDAR_ENABLED = os.getenv("MACRO_CALENDAR_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")

# --- Momentum: Multi-timeframe ---
MOMENTUM_MTF_ENABLED = os.getenv("MOMENTUM_MTF_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
MOMENTUM_MTF_TIMEFRAME = os.getenv("MOMENTUM_MTF_TIMEFRAME", "60").strip()

# --- Momentum: Partial close ---
MOMENTUM_PARTIAL_CLOSE_ENABLED = os.getenv("MOMENTUM_PARTIAL_CLOSE_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
MOMENTUM_PARTIAL_CLOSE_PCT = float(os.getenv("MOMENTUM_PARTIAL_CLOSE_PCT", "0.5") or 0.5)

# --- Momentum: Session filter ---
MOMENTUM_SESSION_FILTER_ENABLED = os.getenv("MOMENTUM_SESSION_FILTER_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
MOMENTUM_SESSION_START_UTC = int(os.getenv("MOMENTUM_SESSION_START_UTC", "8") or 8)
MOMENTUM_SESSION_END_UTC = int(os.getenv("MOMENTUM_SESSION_END_UTC", "22") or 22)

# --- Grid: Profit reinvestment ---
GRID_REINVEST_ENABLED = os.getenv("GRID_REINVEST_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
GRID_REINVEST_PCT = float(os.getenv("GRID_REINVEST_PCT", "0.5") or 0.5)

# --- Momentum: Regime-adaptive parameters ---

# Mean-Reversion RSI thresholds (used when ADX < ADX_RANGE_THRESHOLD)
MOMENTUM_MR_RSI_OVERSOLD = float(os.getenv("MOMENTUM_MR_RSI_OVERSOLD", "25") or 25)
MOMENTUM_MR_RSI_OVERBOUGHT = float(os.getenv("MOMENTUM_MR_RSI_OVERBOUGHT", "75") or 75)
MOMENTUM_MR_SL_PCT = float(os.getenv("MOMENTUM_MR_SL_PCT", "0.015") or 0.015)
MOMENTUM_MR_TP_RSI_EXIT = float(os.getenv("MOMENTUM_MR_TP_RSI_EXIT", "55") or 55)
MOMENTUM_MR_MAX_HOLD_BARS = int(os.getenv("MOMENTUM_MR_MAX_HOLD_BARS", "20") or 20)

# Breakout parameters (used when ADX >= ADX_TREND_THRESHOLD)
MOMENTUM_BO_LOOKBACK = int(os.getenv("MOMENTUM_BO_LOOKBACK", "20") or 20)
MOMENTUM_BO_MIN_VOL_RATIO = float(os.getenv("MOMENTUM_BO_MIN_VOL_RATIO", "1.5") or 1.5)
MOMENTUM_BO_SL_PCT = float(os.getenv("MOMENTUM_BO_SL_PCT", "0.02") or 0.02)
MOMENTUM_BO_TRAIL_ACTIVATE_PCT = float(os.getenv("MOMENTUM_BO_TRAIL_ACTIVATE_PCT", "0.015") or 0.015)
MOMENTUM_BO_TRAIL_DISTANCE_PCT = float(os.getenv("MOMENTUM_BO_TRAIL_DISTANCE_PCT", "0.01") or 0.01)
MOMENTUM_BO_MAX_HOLD_BARS = int(os.getenv("MOMENTUM_BO_MAX_HOLD_BARS", "96") or 96)

# ADX thresholds for regime routing
# ADX < 25: mean-reversion (бэктест: +3.7% за 60д, 65% WR)
MOMENTUM_ADX_RANGE_THRESHOLD = float(os.getenv("MOMENTUM_ADX_RANGE_THRESHOLD", "25") or 25)
# ADX >= 50: breakout (отключён по умолчанию — ложные пробои убыточны на choppy рынке)
MOMENTUM_ADX_TREND_THRESHOLD = float(os.getenv("MOMENTUM_ADX_TREND_THRESHOLD", "50") or 50)


# ─── Валидация ────────────────────────────────────────────────────────

def validate_combo_config() -> list[str]:
    """Проверка конфигурации combo-бота. Возвращает список ошибок."""
    errors: list[str] = []

    # Базовая валидация из config.py
    base_errors = config.validate_config()
    errors.extend(base_errors)

    # Проверка аллокации
    total_alloc = ALLOC_FUNDING_PCT + ALLOC_GRID_PCT + ALLOC_MOMENTUM_PCT
    if total_alloc > 1.01:
        errors.append(
            f"Сумма аллокаций ({total_alloc:.2f}) превышает 100%"
        )

    # Проверка grid
    if GRID_ENABLED:
        if not GRID_SYMBOLS:
            errors.append("GRID_SYMBOLS пусто, но GRID_ENABLED=true")
        if GRID_LEVELS < 2:
            errors.append("GRID_LEVELS должен быть >= 2")
        if GRID_STEP_PCT <= 0 or GRID_STEP_PCT > 0.05:
            errors.append("GRID_STEP_PCT должен быть в (0, 0.05]")

    # Проверка momentum
    if MOMENTUM_ENABLED:
        if not MOMENTUM_SYMBOLS:
            errors.append("MOMENTUM_SYMBOLS пусто, но MOMENTUM_ENABLED=true")
        if MOMENTUM_EMA_FAST >= MOMENTUM_EMA_SLOW:
            errors.append("MOMENTUM_EMA_FAST должен быть < MOMENTUM_EMA_SLOW")
        if MOMENTUM_LEVERAGE < 1 or MOMENTUM_LEVERAGE > 10:
            errors.append("MOMENTUM_LEVERAGE должен быть в [1, 10]")

    return errors
