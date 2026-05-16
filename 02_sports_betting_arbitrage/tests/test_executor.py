"""Tests for BetExecutor from arbitrage.executor."""

from __future__ import annotations

from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from arbitrage.executor import (
    STATUS_FAILED,
    STATUS_NEEDS_HEDGE,
    STATUS_PLACED,
    STATUS_SIMULATED,
    BetExecutor,
)


@pytest.mark.asyncio
async def test_execute_dry_run() -> None:
    """Dry-run mode returns SIMULATED status."""
    with patch("arbitrage.executor.telegram_bot") as mock_tg:
        mock_tg.send_message = patch("arbitrage.executor.telegram_bot.send_message").__enter__()
        executor = BetExecutor()
        executor.dry_run = True
        allocations = [
            {
                "opportunity": {"event": "Test Match", "outcome": "Home", "bookmaker": "bk1", "odds": 2.0},
                "stake_amount": 50.0,
            }
        ]
        results = await executor.execute(allocations)
        assert len(results) == 1
        assert results[0]["status"] == STATUS_SIMULATED


@pytest.mark.asyncio
async def test_execute_surebet_all_success() -> None:
    """All legs succeed in dry_run returns SIMULATED."""
    with patch("arbitrage.executor.telegram_bot") as mock_tg:
        mock_tg.send_message = patch("arbitrage.executor.telegram_bot.send_message").__enter__()
        executor = BetExecutor()
        executor.dry_run = True
        allocations = [
            {
                "opportunity": {"event": "Surebet Match"},
                "stake_amount": 100.0,
                "legs": [
                    {"bookmaker": "bk1", "outcome": "Home", "odds": 2.0, "stake": 50.0},
                    {"bookmaker": "bk2", "outcome": "Away", "odds": 2.1, "stake": 50.0},
                ],
            }
        ]
        results = await executor.execute(allocations)
        assert len(results) == 1
        assert results[0]["status"] == STATUS_SIMULATED


@pytest.mark.asyncio
async def test_execute_surebet_one_fails() -> None:
    """One failing leg triggers NEEDS_HEDGE status."""
    with patch("arbitrage.executor.telegram_bot") as mock_tg:
        mock_tg.send_message = patch("arbitrage.executor.telegram_bot.send_message").__enter__()
        executor = BetExecutor()
        executor.dry_run = False

        allocations = [
            {
                "opportunity": {"event": "Partial Match"},
                "stake_amount": 100.0,
                "legs": [
                    {"bookmaker": "bk1", "outcome": "Home", "odds": 2.0, "stake": 50.0},
                    {"bookmaker": "bk2", "outcome": "Away", "odds": 2.1, "stake": 50.0},
                ],
            }
        ]
        # In non-dry-run mode with no Betfair config, _place_bet returns NOT_IMPLEMENTED
        # which is treated as a failed leg
        results = await executor.execute(allocations)
        assert len(results) == 1
        assert results[0]["status"] == STATUS_NEEDS_HEDGE


@pytest.mark.asyncio
async def test_get_active_bets() -> None:
    """Filters by status to return active bets."""
    with patch("arbitrage.executor.telegram_bot") as mock_tg:
        mock_tg.send_message = patch("arbitrage.executor.telegram_bot.send_message").__enter__()
        executor = BetExecutor()
        executor.dry_run = True
        allocations = [
            {
                "opportunity": {"event": "Active Match", "outcome": "H", "bookmaker": "bk1", "odds": 1.8},
                "stake_amount": 30.0,
            }
        ]
        await executor.execute(allocations)
        active = executor.get_active_bets()
        assert len(active) == 1
        assert active[0]["status"] == STATUS_SIMULATED


@pytest.mark.asyncio
async def test_betfair_placement_success() -> None:
    """Real Betfair placement path: successful bet_id extraction."""
    mock_client_instance = MagicMock()
    mock_client_instance.place_orders = AsyncMock(return_value={
        "status": "SUCCESS",
        "instructionReports": [{"betId": "BET-12345", "status": "SUCCESS"}],
    })
    mock_client_instance.close = AsyncMock()

    with patch("arbitrage.executor.BetfairClient", return_value=mock_client_instance):
        with patch("arbitrage.executor.config") as mock_config:
            mock_config.DRY_RUN = False
            mock_config.BETFAIR_APP_KEY = "test-app-key"
            mock_config.BETFAIR_SESSION_TOKEN = ""

            executor = BetExecutor()
            executor.dry_run = False

            result = await executor._place_bet(
                bookmaker="betfair",
                event="Test Event",
                outcome="Home Win",
                stake=10.0,
                odds=2.5,
                selection_id="12345",
                market_id="1.234567",
                side="BACK",
            )

    assert result["status"] == STATUS_PLACED
    assert result["bet_id"] == "BET-12345"
    assert result["market_id"] == "1.234567"
    assert result["selection_id"] == "12345"
    mock_client_instance.place_orders.assert_called_once()
    mock_client_instance.close.assert_called_once()


@pytest.mark.asyncio
async def test_betfair_placement_retry_exhaustion() -> None:
    """Real Betfair placement path: retries exhausted on failure."""
    mock_client_instance = MagicMock()
    mock_client_instance.place_orders = AsyncMock(return_value={
        "status": "FAILURE",
        "errorCode": "INSUFFICIENT_FUNDS",
    })
    mock_client_instance.close = AsyncMock()

    with patch("arbitrage.executor.BetfairClient", return_value=mock_client_instance):
        with patch("arbitrage.executor.config") as mock_config:
            mock_config.DRY_RUN = False
            mock_config.BETFAIR_APP_KEY = "test-app-key"
            mock_config.BETFAIR_SESSION_TOKEN = ""

            executor = BetExecutor()
            executor.dry_run = False

            result = await executor._place_bet(
                bookmaker="betfair",
                event="Test Event",
                outcome="Home Win",
                stake=10.0,
                odds=2.5,
                selection_id="12345",
                market_id="1.234567",
                side="BACK",
            )

    assert result["status"] == STATUS_FAILED
    assert "INSUFFICIENT_FUNDS" in result["error"]
    # Should have been called 3 times (max_attempts)
    assert mock_client_instance.place_orders.call_count == 3
    mock_client_instance.close.assert_called_once()
