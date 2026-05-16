"""Tests for FEAT-002 (AI layers) and FEAT-003 (integration)."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from typing import Any
from unittest.mock import patch

import pytest

# Ensure test DB is in-memory
os.environ.setdefault("ARB_DB_PATH", ":memory:")


# --- B1: LinePredictor ---


def test_line_predictor_instantiation():
    """LinePredictor can be created."""
    from arbitrage.ai_line_predictor import LinePredictor

    predictor = LinePredictor()
    assert predictor is not None


def test_compute_urgency_factor_stable():
    """compute_urgency_factor returns 1.0 for stable prediction."""
    from arbitrage.ai_line_predictor import compute_urgency_factor

    prediction = {"direction": "stable", "magnitude": 0.0, "confidence": 50, "timeframe_min": 15}
    assert compute_urgency_factor(prediction) == 1.0


def test_compute_urgency_factor_down_high_confidence():
    """compute_urgency_factor returns >1.0 for down+high confidence."""
    from arbitrage.ai_line_predictor import compute_urgency_factor

    prediction = {"direction": "down", "magnitude": 0.3, "confidence": 90, "timeframe_min": 5}
    factor = compute_urgency_factor(prediction)
    assert factor > 1.0
    assert factor <= 2.0


# --- B2: NewsScanner ---


def test_news_scanner_instantiation():
    """NewsScanner can be created."""
    from arbitrage.ai_news_scanner import NewsScanner

    scanner = NewsScanner()
    assert scanner is not None


# --- B3: ThresholdOptimizer ---


def test_optimizer_instantiation():
    """ThresholdOptimizer can be created."""
    from arbitrage.ai_optimizer import ThresholdOptimizer

    optimizer = ThresholdOptimizer()
    assert optimizer is not None


# --- B4: BookmakerClassifier ---


def test_bk_classifier_instantiation():
    """BookmakerClassifier can be created."""
    from arbitrage.ai_bk_classifier import BookmakerClassifier

    classifier = BookmakerClassifier()
    assert classifier is not None


# --- B5: OddsAnomalyDetector ---


@pytest.mark.asyncio
async def test_anomaly_detector_low_profit():
    """OddsAnomalyDetector returns is_anomaly=False when profit <= 5.0."""
    from arbitrage.ai_anomaly_detector import OddsAnomalyDetector
    from unittest.mock import AsyncMock

    detector = OddsAnomalyDetector()
    mock_session = AsyncMock()
    opportunity = {"profit_pct": 3.0, "sport": "soccer_epl", "event": "test"}
    result = await detector.detect(mock_session, opportunity)
    assert result["is_anomaly"] is False


# --- B6: EventCorrelation ---


def test_correlation_instantiation():
    """EventCorrelation can be created."""
    from arbitrage.ai_correlation import EventCorrelation

    correlation = EventCorrelation()
    assert correlation is not None


# --- B7: WithdrawalStrategy ---


def test_withdrawal_instantiation():
    """WithdrawalStrategy can be created."""
    from arbitrage.ai_withdrawal import WithdrawalStrategy

    strategy = WithdrawalStrategy()
    assert strategy is not None


# --- B8: MarketMaker ---


def test_market_maker_instantiation():
    """MarketMaker can be created."""
    from arbitrage.betfair_stream import MarketMaker

    maker = MarketMaker()
    assert maker is not None


# --- Memory: BK Classification ---


def test_bk_classification_memory(tmp_path):
    """save and load bk_classification in memory."""
    db_path = str(tmp_path / "test.db")

    import arbitrage.memory as mem

    def patched_connect():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    with patch.object(mem, "_connect", patched_connect):
        mem.init_db()
        mem.save_bk_classification("pinnacle", "low", 90, "Safe to use")
        mem.save_bk_classification("bet365", "high", 20, "Reduce activity")

        classifications = mem.get_all_bk_classifications()
        assert len(classifications) == 2

        single = mem.get_bk_classification("pinnacle")
        assert single is not None
        assert single["risk_level"] == "low"
        assert single["days_to_cut"] == 90


# --- Telegram Bot: Keyboard and Handlers ---


def test_telegram_keyboard_has_5_rows():
    """set_keyboard() returns 5 rows."""
    from arbitrage.telegram_bot import set_keyboard

    kb = set_keyboard()
    rows = kb["inline_keyboard"]
    assert len(rows) == 5


def test_telegram_handlers_registered():
    """CB_AI_FORECAST and CB_WITHDRAWAL in _HANDLERS."""
    from arbitrage.telegram_bot import (
        CB_AI_FORECAST,
        CB_WITHDRAWAL,
        _HANDLERS,
    )

    assert CB_AI_FORECAST in _HANDLERS
    assert CB_WITHDRAWAL in _HANDLERS


# --- Main module imports ---


def test_main_imports():
    """import arbitrage.main works without errors."""
    import arbitrage.main  # noqa: F401


# --- Retry module ---


def test_retry_module_exists():
    """from arbitrage.retry import retry_request works."""
    from arbitrage.retry import retry_request  # noqa: F401

    assert callable(retry_request)


# --- Logging config ---


def test_logging_config_exists():
    """from arbitrage.logging_config import setup_logging works."""
    from arbitrage.logging_config import setup_logging  # noqa: F401

    assert callable(setup_logging)
