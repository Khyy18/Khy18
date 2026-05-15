"""Tests for BetExecutor from arbitrage.executor."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from arbitrage.executor import (
    STATUS_NEEDS_HEDGE,
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
