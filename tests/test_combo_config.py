"""Тесты combo_config.py."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import combo_config as cfg


def test_default_allocations():
    """Дефолтные аллокации = 50/30/20."""
    assert cfg.ALLOC_FUNDING_PCT == 0.50
    assert cfg.ALLOC_GRID_PCT == 0.30
    assert cfg.ALLOC_MOMENTUM_PCT == 0.20


def test_allocations_sum_to_one():
    """Сумма аллокаций = 1.0."""
    total = cfg.ALLOC_FUNDING_PCT + cfg.ALLOC_GRID_PCT + cfg.ALLOC_MOMENTUM_PCT
    assert abs(total - 1.0) < 0.001


def test_default_capital():
    """Дефолтный капитал = 550."""
    assert cfg.TOTAL_CAPITAL_USDT == 550.0


def test_global_drawdown_threshold():
    """Порог kill-switch = 15%."""
    assert cfg.GLOBAL_MAX_DRAWDOWN_PCT == 0.15


def test_grid_defaults():
    """Grid: дефолтные параметры."""
    assert "BTCUSDT" in cfg.GRID_SYMBOLS
    assert "ETHUSDT" in cfg.GRID_SYMBOLS
    assert cfg.GRID_LEVELS == 10
    assert 0 < cfg.GRID_STEP_PCT < 0.05
    assert cfg.GRID_LEVERAGE >= 1


def test_momentum_defaults():
    """Momentum: дефолтные параметры."""
    assert "BTCUSDT" in cfg.MOMENTUM_SYMBOLS
    assert cfg.MOMENTUM_EMA_FAST < cfg.MOMENTUM_EMA_SLOW
    assert cfg.MOMENTUM_LEVERAGE == 3
    assert cfg.MOMENTUM_STOP_LOSS_PCT > 0
    assert cfg.MOMENTUM_MAX_POSITIONS >= 1


def test_validate_combo_config_ok():
    """Валидация с дефолтными значениями (без .env) — только Telegram ошибки."""
    errors = cfg.validate_combo_config()
    # Без TELEGRAM_TOKEN будет ошибка — это OK
    # Не должно быть ошибок от grid/momentum/alloc
    alloc_errors = [e for e in errors if "аллокац" in e.lower()]
    grid_errors = [e for e in errors if "grid" in e.lower()]
    mom_errors = [e for e in errors if "momentum" in e.lower()]
    assert alloc_errors == []
    assert grid_errors == []
    assert mom_errors == []


def test_grid_exchange_default():
    """Биржа для grid по умолчанию — bybit."""
    assert cfg.GRID_EXCHANGE == "bybit"


def test_momentum_exchange_default():
    """Биржа для momentum по умолчанию — bybit."""
    assert cfg.MOMENTUM_EXCHANGE == "bybit"
