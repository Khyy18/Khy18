"""Tests for kelly_fraction and BankrollAllocator from arbitrage.ai_allocator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from arbitrage.ai_allocator import kelly_fraction


class TestKellyFraction:
    """Tests for kelly_fraction function."""

    def test_kelly_fraction_positive_edge(self) -> None:
        """odds=2.0, prob=0.6 -> f*=0.2."""
        # b = 2.0 - 1 = 1.0
        # f* = (1.0*0.6 - 0.4) / 1.0 = 0.2
        result = kelly_fraction(2.0, 0.6)
        assert abs(result - 0.2) < 1e-6

    def test_kelly_fraction_no_edge(self) -> None:
        """prob=0.4, odds=2.0 -> f*=0 (negative edge clamped to 0)."""
        # b = 1.0, f* = (1.0*0.4 - 0.6) / 1.0 = -0.2 -> clamped to 0
        result = kelly_fraction(2.0, 0.4)
        assert result == 0.0

    def test_kelly_fraction_capped(self) -> None:
        """Extreme values don't exceed 1.0."""
        # odds=10.0, prob=0.99 -> b=9, f*=(9*0.99-0.01)/9 = 0.988.. <= 1.0
        result = kelly_fraction(10.0, 0.99)
        assert result <= 1.0

    def test_kelly_fraction_zero_b(self) -> None:
        """odds=1.0 returns 0 (b=0)."""
        result = kelly_fraction(1.0, 0.6)
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_allocator_surebet_mode(self) -> None:
        """sizing_mode=surebet calculates legs proportionally."""
        import aiohttp

        with patch("arbitrage.ai_allocator.ai_router", None):
            from arbitrage.ai_allocator import BankrollAllocator

            # Create mock session
            mock_session = AsyncMock(spec=aiohttp.ClientSession)
            allocator = BankrollAllocator(session=mock_session, bankroll=1000.0)

            opportunities = [
                {
                    "sizing_mode": "surebet",
                    "profit_pct": 3.0,
                    "odds": [2.0, 3.0],
                    "bookmakers": ["bk1", "bk2"],
                    "details": {"outcomes": ["Home", "Away"]},
                }
            ]

            result = await allocator.allocate(opportunities, 1000.0)
            assert len(result) == 1
            alloc = result[0]
            assert "legs" in alloc
            assert len(alloc["legs"]) == 2
            # Verify legs stake sum roughly equals total stake
            total_leg_stake = sum(leg["stake"] for leg in alloc["legs"])
            assert abs(total_leg_stake - alloc["stake_amount"]) < 0.1
