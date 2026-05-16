"""Integration tests with real Odds API.

These tests require ODDS_API_KEY environment variable.
Skip automatically if not set.
"""

from __future__ import annotations

import os

import pytest
import aiohttp

pytestmark = pytest.mark.skipif(
    not os.getenv("ODDS_API_KEY"),
    reason="ODDS_API_KEY not set - skipping integration tests",
)


@pytest.mark.asyncio
async def test_odds_api_sports_list() -> None:
    """GET /v4/sports returns a list of sports."""
    from arbitrage.odds_api import OddsAPIClient

    async with aiohttp.ClientSession() as session:
        client = OddsAPIClient(session=session)
        # Use discover_active_sports which calls /v4/sports
        sports = await client.discover_active_sports()
        assert isinstance(sports, list)
        assert len(sports) > 0


@pytest.mark.asyncio
async def test_odds_api_soccer_epl() -> None:
    """GET odds for soccer_epl returns valid structure."""
    from arbitrage.odds_api import OddsAPIClient

    async with aiohttp.ClientSession() as session:
        client = OddsAPIClient(session=session)
        events = await client.get_odds("soccer_epl")
        assert isinstance(events, list)
        # May be empty if no games, but structure should be valid
        if events:
            event = events[0]
            assert "bookmakers" in event or "id" in event


@pytest.mark.asyncio
async def test_scanner_on_real_data() -> None:
    """scanner.find_surebets() on real data doesn't crash."""
    from arbitrage.odds_api import OddsAPIClient
    from arbitrage.scanner import ArbitrageScanner

    async with aiohttp.ClientSession() as session:
        client = OddsAPIClient(session=session)
        events = await client.get_odds("soccer_epl")
        scanner = ArbitrageScanner()
        # Should not raise
        result = scanner.find_surebets(events)
        assert isinstance(result, list)


@pytest.mark.asyncio
async def test_pinnacle_extraction_real_data() -> None:
    """PinnacleClient.extract_pinnacle_from_odds_api() works on real data."""
    from arbitrage.odds_api import OddsAPIClient
    from arbitrage.pinnacle_api import PinnacleClient

    async with aiohttp.ClientSession() as session:
        client = OddsAPIClient(session=session)
        events = await client.get_odds("soccer_epl")
        sharp_probs = PinnacleClient.extract_pinnacle_from_odds_api(events)
        assert isinstance(sharp_probs, dict)
