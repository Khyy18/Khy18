"""Tests for compute_spread_probability from arbitrage.middles."""

from __future__ import annotations

from arbitrage.middles import GOAL_DIFF_PROBS, compute_spread_probability


class TestComputeSpreadProbability:
    """Tests for compute_spread_probability function."""

    def test_soccer_corridor_3_to_4(self) -> None:
        """Soccer corridor [3, 4] should not include endpoints (integer boundaries)."""
        # corridor_low=3, corridor_high=4 -> both integers,
        # k_start = floor(3)+1 = 4, k_end = ceil(4)-1 = 3
        # so no k in range, should be 0
        result = compute_spread_probability(3.0, 4.0, "soccer_epl")
        # Actually with integer boundaries, k_start=4, k_end=3 -> empty range
        assert result == 0.0

    def test_soccer_corridor_3_5(self) -> None:
        """Soccer corridor [3, 5]: includes k=4 (integer boundaries excluded)."""
        # corridor_low=3 (int), corridor_high=5 (int)
        # k_start = floor(3)+1 = 4, k_end = ceil(5)-1 = 4
        # So k=4 only
        result = compute_spread_probability(3.0, 5.0, "soccer_epl")
        expected = GOAL_DIFF_PROBS.get(4, 0.001)
        assert abs(result - expected) < 1e-6

    def test_soccer_corridor_half_integer(self) -> None:
        """Soccer corridor [3.5, 4.5]: includes k=4."""
        result = compute_spread_probability(3.5, 4.5, "soccer_epl")
        expected = GOAL_DIFF_PROBS.get(4, 0.001)
        assert abs(result - expected) < 1e-6

    def test_soccer_corridor_wide(self) -> None:
        """Soccer corridor [0.5, 3.5]: includes k=1, 2, 3."""
        result = compute_spread_probability(0.5, 3.5, "soccer_epl")
        expected = GOAL_DIFF_PROBS.get(1, 0) + GOAL_DIFF_PROBS.get(2, 0) + GOAL_DIFF_PROBS.get(3, 0)
        assert abs(result - expected) < 1e-6
        assert result > 0.3  # 0.22 + 0.12 + 0.04 = 0.38

    def test_basketball_returns_nonzero(self) -> None:
        """Basketball corridor uses normal approximation."""
        result = compute_spread_probability(3.5, 5.5, "basketball_nba")
        assert 0.0 < result < 1.0

    def test_unknown_sport_naive(self) -> None:
        """Unknown sport uses naive fallback: width / corridor_high."""
        result = compute_spread_probability(2.0, 6.0, "unknown_sport")
        # width=4, corridor_high=6 -> 4/6 ~ 0.6667
        assert abs(result - (4.0 / 6.0)) < 1e-6

    def test_football_prefix_matches_soccer(self) -> None:
        """Sport starting with 'football' should use soccer logic."""
        result = compute_spread_probability(0.5, 2.5, "football_premier")
        expected = GOAL_DIFF_PROBS.get(1, 0) + GOAL_DIFF_PROBS.get(2, 0)
        assert abs(result - expected) < 1e-6

    def test_soccer_negative_corridor(self) -> None:
        """Soccer corridor with negative values [-2.5, -0.5]: includes k=-2, -1."""
        result = compute_spread_probability(-2.5, -0.5, "soccer_epl")
        expected = GOAL_DIFF_PROBS.get(-2, 0) + GOAL_DIFF_PROBS.get(-1, 0)
        assert abs(result - expected) < 1e-6
