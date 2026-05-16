"""Конфигурация КОМБО-бота (funding + grid).

Расширяет config.py дополнительными параметрами для grid-стратегии.
Глобальные параметры (Telegram, биржи) берутся из config.py.
"""

from __future__ import annotations

import os

import config  # noqa: F401 — base config, все ключи доступны через config.*


# ─── Аллокация капитала ───────────────────────────────────────────────
# Funding-арб 75%: delta-neutral, 15-30% APR, стабильный доход.
# Grid 25%: зарабатывает в боковике (70-80% времени).
ALLOC_FUNDING_PCT = float(os.getenv("ALLOC_FUNDING_PCT", "0.75") or 0.75)
ALLOC_GRID_PCT = float(os.getenv("ALLOC_GRID_PCT", "0.25") or 0.25)

# Стартовый капитал (USDT). Если 0 — берётся из суммы балансов на биржах.
TOTAL_CAPITAL_USDT = float(os.getenv("TOTAL_CAPITAL_USDT", "550") or 550)


# ─── Глобальный kill-switch ───────────────────────────────────────────
# Если суммарный drawdown по ВСЕМ стратегиям > порога — ВСЕ стратегии
# останавливаются. Снимается только вручную через Telegram.
GLOBAL_MAX_DRAWDOWN_PCT = float(os.getenv("GLOBAL_MAX_DRAWDOWN_PCT", "0.15") or 0.15)


# ─── Grid-бот ─────────────────────────────────────────────────────────
# Символы для grid-торговли.
# Altcoins (SOL, DOGE) дают в 3-5x больше grid-циклов из-за высокой волатильности
GRID_SYMBOLS: list[str] = [
    s.strip() for s in os.getenv("GRID_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT,DOGEUSDT").split(",") if s.strip()
]

# Биржа для grid (одна). По умолчанию bybit.
GRID_EXCHANGE = os.getenv("GRID_EXCHANGE", "bybit").strip().lower()

# Количество уровней сетки (buy + sell ордера).
GRID_LEVELS = int(os.getenv("GRID_LEVELS", "12") or 12)

# Шаг сетки в процентах от текущей цены.
# 0.005 = 0.5% между уровнями. При 12 уровнях покрываем ±3%.
GRID_STEP_PCT = float(os.getenv("GRID_STEP_PCT", "0.005") or 0.005)

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


# ─── Grid: защита от unrealized loss ───────────────────────────────────
# Если суммарный unrealized loss по grid (все filled buy без matched sell)
# превышает этот % от equity → force close all grid + rebuild.
GRID_MAX_UNREALIZED_LOSS_PCT = float(os.getenv("GRID_MAX_UNREALIZED_LOSS_PCT", "0.05") or 0.05)

# ─── Spread guard ─────────────────────────────────────────────────────
# Если spread (ask - bid) / mid > порога → не размещать ордера (ликвидность
# испарилась, maintenance, flash crash). 0.005 = 0.5%.
MAX_SPREAD_PCT = float(os.getenv("MAX_SPREAD_PCT", "0.005") or 0.005)

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


# ─── Риск-менеджмент ──────────────────────────────────────────────────
# Per-strategy daily loss limit (доля от equity). 0 = выключено.
# Если стратегия потеряла больше лимита за UTC-сутки — пауза до завтра.
RISK_DAILY_LOSS_GRID_PCT = float(os.getenv("RISK_DAILY_LOSS_GRID_PCT", "0.02") or 0.02)

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

# --- Grid: Profit reinvestment ---
GRID_REINVEST_ENABLED = os.getenv("GRID_REINVEST_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
GRID_REINVEST_PCT = float(os.getenv("GRID_REINVEST_PCT", "0.7") or 0.7)


# ─── Валидация ────────────────────────────────────────────────────────

def validate_combo_config() -> list[str]:
    """Проверка конфигурации combo-бота. Возвращает список ошибок."""
    errors: list[str] = []

    # Базовая валидация из config.py
    base_errors = config.validate_config()
    errors.extend(base_errors)

    # Проверка аллокации
    total_alloc = ALLOC_FUNDING_PCT + ALLOC_GRID_PCT
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

    return errors
