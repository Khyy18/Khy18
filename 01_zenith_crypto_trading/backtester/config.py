"""Константы и конфиг бэктестера (комиссии, проскальзывание, таймфреймы).

Модели исполнения ориентированы на Bybit V5 linear-perpetual:
  - taker 0.055% (MARKET/IOC),
  - maker 0.02%  (PostOnly limit),
  - market-ордер теряет 1 тик спреда в каждую сторону,
  - PostOnly отменяется, если уровень лимита уже «за» противоположной стороной
    следующего бара (skip-on-cross).

Все значения по умолчанию подогнаны под пару BTCUSDT на Bybit,
но при необходимости прокидываются из CLI или из `config.py` репозитория.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# --- Комиссии и проскальзывание ---
TAKER_FEE: float = 0.00055   # 0.055 %
MAKER_FEE: float = 0.00020   # 0.020 %
MARKET_SLIPPAGE_TICKS: int = 1

# Дополнительный slippage для market-ордеров в bps от цены. На liquid-парах
# Bybit/OKX 1 тик = 0.0001% от цены - это нереалистично мало для market.
# Реальный edge teryaitsya бывает 1-5 bps в зависимости от размера ордера и
# мгновенной ликвидности. Берём 2 bps (0.02%) как консервативное среднее
# для размеров до $1000 на BTC/ETH/SOL.
MARKET_SLIPPAGE_BPS: float = 2.0

# Funding-фи Bybit/OKX linear-perp: примерно ±0.01% каждые 8 часов
# (UTC 00:00, 08:00, 16:00). Знак зависит от стороны: long платит при
# положительном funding, short получает; при отрицательном наоборот.
# Усреднённое за длинные периоды значение - близко к нулю, но в HONEST-режиме
# мы списываем абсолютное значение в обе стороны: симулируем "среднюю
# плату за плечо" 0.01% / 8ч ~= 0.03% в сутки ~= 11% в год. Для шортов
# это завышенная оценка костов, но именно так backtest становится
# консервативным и не выдаёт фантомного PnL за счёт удержания позиции.
FUNDING_RATE_PER_8H: float = 0.0001       # 0.01 % каждые 8 часов
FUNDING_INTERVAL_MS: int = 8 * 60 * 60 * 1000

# Шаг цены (tickSize) по умолчанию для основных инструментов.
# Реальные значения берутся из Bybit V5 /v5/market/instruments-info; здесь
# задано лишь для оффлайнового бэктеста, чтобы не ходить в сеть.
DEFAULT_TICK_SIZE: dict[str, float] = {
    "BTCUSDT": 0.1,
    "ETHUSDT": 0.01,
    "SOLUSDT": 0.01,
}

# Длительность таймфреймов в минутах (для resample.py).
TF_MINUTES: dict[str, int] = {
    "1m": 1,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

PRIMARY_TF: str = "1h"
HIGHER_TFS: tuple[str, ...] = ("4h", "1d")

# Каталог для загруженных CSV/ZIP Binance. Держим рядом с пакетом,
# чтобы `python -m backtester.run` без флагов сразу находил кэш.
DEFAULT_CACHE_DIR: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data",
)


def _load_risk_defaults() -> tuple[float, float]:
    """Подтянуть RISK_PER_TRADE и GLOBAL_RISK_CAP из корневого config.py.

    Импорт выполняется лениво, чтобы избежать циклических зависимостей
    при раннем импорте пакета (например, если корневой config.py ещё
    не существует в unit-тестах)."""
    risk_per_trade = 0.01
    global_risk_cap = 0.03
    try:
        import config as root_config  # type: ignore

        risk_per_trade = float(getattr(root_config, "RISK_PER_TRADE", risk_per_trade))
        global_risk_cap = float(getattr(root_config, "GLOBAL_RISK_CAP", global_risk_cap))
    except Exception:
        # При любой проблеме используем безопасные дефолты.
        pass
    return risk_per_trade, global_risk_cap


_RISK_PER_TRADE_DEFAULT, _GLOBAL_RISK_CAP_DEFAULT = _load_risk_defaults()


@dataclass
class BacktesterConfig:
    """Контейнер параметров движка. Все значения по умолчанию совпадают
    с продовыми (Bybit linear-perp) для консервативных оценок."""

    initial_equity: float = 10000.0
    taker_fee: float = TAKER_FEE
    maker_fee: float = MAKER_FEE
    market_slippage_ticks: int = MARKET_SLIPPAGE_TICKS
    market_slippage_bps: float = MARKET_SLIPPAGE_BPS
    funding_rate_per_8h: float = FUNDING_RATE_PER_8H
    funding_interval_ms: int = FUNDING_INTERVAL_MS
    apply_funding: bool = True
    risk_per_trade: float = _RISK_PER_TRADE_DEFAULT
    global_risk_cap: float = _GLOBAL_RISK_CAP_DEFAULT
    per_symbol_max_positions: int = 1
