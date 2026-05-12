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
    risk_per_trade: float = _RISK_PER_TRADE_DEFAULT
    global_risk_cap: float = _GLOBAL_RISK_CAP_DEFAULT
    per_symbol_max_positions: int = 1
