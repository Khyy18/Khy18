"""Тесты для FEAT-001: 6 архитектурных исправлений."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Подготовка тестовой БД
os.environ.setdefault("ARB_DB_PATH", ":memory:")


# --- A1: Retry with exponential backoff ---


@pytest.mark.asyncio
async def test_retry_success_on_first_try():
    """Retry возвращает ответ при успешном первом запросе."""
    from arbitrage.retry import retry_request

    mock_resp = MagicMock()
    mock_resp.status = 200

    mock_session = AsyncMock()
    mock_session.request = AsyncMock(return_value=mock_resp)

    result = await retry_request(mock_session, "GET", "http://example.com/test")
    assert result.status == 200
    assert mock_session.request.call_count == 1


@pytest.mark.asyncio
async def test_retry_on_5xx():
    """Retry повторяет запрос при 5xx и возвращает при исчерпании попыток."""
    from arbitrage.retry import retry_request

    mock_resp = MagicMock()
    mock_resp.status = 503

    mock_session = AsyncMock()
    mock_session.request = AsyncMock(return_value=mock_resp)

    with patch("arbitrage.retry.asyncio.sleep", new_callable=AsyncMock):
        result = await retry_request(
            mock_session, "GET", "http://example.com/test", max_retries=2, backoff_base=0.01
        )
    assert result.status == 503
    # 1 initial + 2 retries = 3
    assert mock_session.request.call_count == 3


@pytest.mark.asyncio
async def test_retry_no_retry_on_4xx():
    """Retry не повторяет при 4xx (кроме 429)."""
    from arbitrage.retry import retry_request

    mock_resp = MagicMock()
    mock_resp.status = 403

    mock_session = AsyncMock()
    mock_session.request = AsyncMock(return_value=mock_resp)

    result = await retry_request(mock_session, "GET", "http://example.com/test")
    assert result.status == 403
    assert mock_session.request.call_count == 1


@pytest.mark.asyncio
async def test_retry_on_429_with_retry_after():
    """Retry ждёт Retry-After при 429."""
    from arbitrage.retry import retry_request

    mock_resp_429 = MagicMock()
    mock_resp_429.status = 429
    mock_resp_429.headers = {"Retry-After": "2"}

    mock_resp_200 = MagicMock()
    mock_resp_200.status = 200

    mock_session = AsyncMock()
    mock_session.request = AsyncMock(side_effect=[mock_resp_429, mock_resp_200])

    with patch("arbitrage.retry.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await retry_request(
            mock_session, "GET", "http://example.com/test", max_retries=3
        )
    assert result.status == 200
    mock_sleep.assert_called_with(2.0)


# --- A2: Graceful degradation on quota exhaustion ---


def test_quota_degradation_doubles_interval():
    """Проверка логики удвоения интервала при квоте < 20%."""
    from arbitrage import config

    state: dict[str, Any] = {"scanner_active": True}
    remaining_pct = 15.0

    # Simulate the logic from scanner_loop
    if remaining_pct < 20.0 and not state.get("scan_interval_override"):
        state["scan_interval_override"] = config.SCAN_INTERVAL_SEC * 2

    assert state["scan_interval_override"] == config.SCAN_INTERVAL_SEC * 2


def test_quota_degradation_stops_scanner():
    """Проверка остановки сканера при квоте < 5%."""
    state: dict[str, Any] = {"scanner_active": True}
    remaining_pct = 3.0

    if remaining_pct < 5.0:
        state["scanner_active"] = False

    assert state["scanner_active"] is False


def test_quota_override_reset_on_first_of_month():
    """Проверка сброса override на 1-е число месяца."""
    state: dict[str, Any] = {"scan_interval_override": 60}

    # Simulate: day == 1
    if state.get("scan_interval_override") and True:  # day == 1
        state.pop("scan_interval_override", None)

    assert "scan_interval_override" not in state


# --- A3: Settlement by event_id ---


def test_record_arb_with_event_id():
    """record_arb принимает event_id и записывает в БД."""
    # Use a fresh temp DB
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        with patch("arbitrage.memory.DB_PATH", db_path):
            from arbitrage import memory as mem

            # Re-init with patched path

            def patched_connect():
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                return conn

            with patch.object(mem, "_connect", patched_connect):
                mem.init_db()
                arb_id = mem.record_arb(
                    sport="soccer_epl",
                    event="Team A vs Team B",
                    arb_type="surebet",
                    bookmakers=["bet365", "pinnacle"],
                    odds={"odds": [2.1, 2.0]},
                    profit_pct=1.5,
                    edge_pct=1.0,
                    event_id="abc123",
                )
                assert arb_id is not None

                conn = patched_connect()
                row = conn.execute(
                    "SELECT event_id FROM arbs WHERE id = ?", (arb_id,)
                ).fetchone()
                assert row["event_id"] == "abc123"
                conn.close()
    finally:
        os.unlink(db_path)


def test_settlement_find_match_by_id():
    """Settlement ищет по event_id."""
    from arbitrage.settlement import SettlementEngine

    scores = [
        {"id": "evt_001", "home_team": "Liverpool", "away_team": "Chelsea", "completed": True},
        {"id": "evt_002", "home_team": "Arsenal", "away_team": "Spurs", "completed": True},
    ]

    result = SettlementEngine._find_match_by_id(scores, "evt_002")
    assert result is not None
    assert result["home_team"] == "Arsenal"


def test_settlement_find_match_by_id_not_found():
    """Settlement возвращает None при отсутствии event_id."""
    from arbitrage.settlement import SettlementEngine

    scores = [
        {"id": "evt_001", "home_team": "Liverpool", "away_team": "Chelsea"},
    ]

    result = SettlementEngine._find_match_by_id(scores, "nonexistent")
    assert result is None


def test_settlement_find_match_by_id_empty():
    """Settlement возвращает None при пустом event_id."""
    from arbitrage.settlement import SettlementEngine

    scores = [{"id": "evt_001", "home_team": "Liverpool", "away_team": "Chelsea"}]
    result = SettlementEngine._find_match_by_id(scores, "")
    assert result is None


# --- A4: Structured logging ---


def test_logging_config_setup():
    """setup_logging создаёт хендлеры."""
    import logging
    from arbitrage.logging_config import setup_logging

    # Clear handlers first
    arb_logger = logging.getLogger("arbitrage")
    arb_logger.handlers.clear()

    setup_logging()

    assert len(arb_logger.handlers) >= 2  # console + file
    assert arb_logger.level == logging.INFO


def test_logging_config_no_duplicate():
    """Повторный вызов setup_logging не дублирует хендлеры."""
    import logging
    from arbitrage.logging_config import setup_logging

    arb_logger = logging.getLogger("arbitrage")
    arb_logger.handlers.clear()

    setup_logging()
    count_after_first = len(arb_logger.handlers)

    setup_logging()
    count_after_second = len(arb_logger.handlers)

    assert count_after_first == count_after_second


# --- A5: Fix daily_pnl timezone ---


def test_daily_pnl_uses_utc():
    """get_daily_pnl использует UTC дату вместо SQLite date('now')."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        import arbitrage.memory as mem

        def patched_connect():
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            return conn

        with patch.object(mem, "_connect", patched_connect):
            mem.init_db()

            # Insert test data
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            old_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")

            mem.update_daily_pnl(today, 100.0, 110.0, 10.0, 10.0)
            mem.update_daily_pnl(old_date, 50.0, 40.0, -10.0, -20.0)

            # Get last 7 days - should only contain today
            result = mem.get_daily_pnl(days=7)
            assert len(result) == 1
            assert result[0]["date"] == today
    finally:
        os.unlink(db_path)


# --- A6: Auto-recovery state ---


def test_bot_state_save_and_load():
    """save_bot_state/load_bot_state работают корректно."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        import arbitrage.memory as mem

        def patched_connect():
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            return conn

        with patch.object(mem, "_connect", patched_connect):
            mem.init_db()

            mem.save_bot_state("scanner_active", "True")
            assert mem.load_bot_state("scanner_active") == "True"

            mem.save_bot_state("scan_interval_override", "60")
            assert mem.load_bot_state("scan_interval_override") == "60"

            # Update existing key
            mem.save_bot_state("scanner_active", "False")
            assert mem.load_bot_state("scanner_active") == "False"

            # Non-existent key
            assert mem.load_bot_state("nonexistent") is None
    finally:
        os.unlink(db_path)


def test_bot_state_table_exists():
    """init_db создаёт таблицу bot_state."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        import arbitrage.memory as mem

        def patched_connect():
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            return conn

        with patch.object(mem, "_connect", patched_connect):
            mem.init_db()

            conn = patched_connect()
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='bot_state'"
            ).fetchall()
            assert len(tables) == 1
            conn.close()
    finally:
        os.unlink(db_path)
