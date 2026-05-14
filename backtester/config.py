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

# Funding rate для perpetual futures: позиция платит/получает funding каждые
# 8 часов в зависимости от стороны и направления rate. Среднее по BTCUSDT
# на Bybit V5 за 2024-2026: ~0.01% / 8ч (LONG чаще платит, SHORT чаще получает,
# но усреднённо около нуля). Для ЧЕСТНОЙ оценки backtest'а считаем абсолютное
# списание 0.01%/8ч на ЛЮБУЮ сторону — это консервативный pessimistic case.
# В реальности SHORT иногда получает положительный funding и улучшает PnL,
# но в backtest мы предпочитаем недооценить P&L, чем переоценить.
FUNDING_RATE_PER_8H: float = 0.0001   # 0.01 %, абсолютное

# Дополнительный slippage в bps, применяется на ВЫПОЛНЕНИИ market-ордера
# поверх 1 тика. Реальный slippage на BTCUSDT при $1-5K notional — 1-3 bps,
# на mid-cap альтах (DOGE/AVAX) — 3-8 bps. Берём 2 bps как разумную середину.
EXECUTION_SLIPPAGE_BPS: float = 2.0   # 0.02 % сверх 1 тика

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
    funding_rate_per_8h: float = FUNDING_RATE_PER_8H
    execution_slippage_bps: float = EXECUTION_SLIPPAGE_BPS
    risk_per_trade: float = _RISK_PER_TRADE_DEFAULT
    global_risk_cap: float = _GLOBAL_RISK_CAP_DEFAULT
    per_symbol_max_positions: int = 1
