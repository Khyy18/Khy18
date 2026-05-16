"""Tests for ArbRanker from arbitrage.ranker."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from arbitrage.ranker import ArbRanker


class TestArbRanker:
    """Tests for ArbRanker."""

    def test_rank_sorts_by_composite(self) -> None:
        """Higher profit + ai_score ranked first."""
        ranker = ArbRanker(top_n=10)
        opps = [
            {"profit_pct": 2.0, "ai_score": 80, "sport": "soccer_epl", "timestamp": time.time()},
            {"profit_pct": 5.0, "ai_score": 90, "sport": "soccer_epl", "timestamp": time.time()},
            {"profit_pct": 1.0, "ai_score": 50, "sport": "soccer_epl", "timestamp": time.time()},
        ]
        result = ranker.rank(opps)
        scores = [r["composite_score"] for r in result]
        assert scores == sorted(scores, reverse=True)
        # Second item (profit=5.0, ai=90) should be first
        assert result[0]["profit_pct"] == 5.0

    def test_liquidity_factor_major(self) -> None:
        """soccer_epl returns 1.0."""
        factor = ArbRanker._liquidity_factor("soccer_epl")
        assert factor == 1.0

    def test_liquidity_factor_minor(self) -> None:
        """Unknown sport returns 0.6."""
        factor = ArbRanker._liquidity_factor("unknown_league")
        assert factor == 0.6

    def test_freshness_factor_fresh(self) -> None:
        """Just-created timestamp returns ~1.0."""
        opp = {"timestamp": time.time()}
        factor = ArbRanker._freshness_factor(opp)
        assert 0.95 <= factor <= 1.0

    def test_freshness_factor_old(self) -> None:
        """300s old returns 0.5 (minimum)."""
        old_ts = time.time() - 300.0
        opp = {"timestamp": old_ts}
        factor = ArbRanker._freshness_factor(opp)
        assert abs(factor - 0.5) < 0.05

    def test_top_n_respected(self) -> None:
        """Only top_n items are returned."""
        ranker = ArbRanker(top_n=2)
        opps = [
            {"profit_pct": float(i), "ai_score": 80, "sport": "soccer_epl", "timestamp": time.time()}
            for i in range(5)
        ]
        result = ranker.rank(opps)
        assert len(result) == 2
