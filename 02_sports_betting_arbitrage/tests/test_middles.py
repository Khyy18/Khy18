"""Tests for MiddleScanner and Poisson functions from arbitrage.middles."""

from __future__ import annotations

import math

from arbitrage.middles import (
    MiddleScanner,
    compute_poisson_probability,
    poisson_pmf,
)


class TestPoissonPmf:
    """Tests for poisson_pmf function."""

    def test_poisson_pmf_k0(self) -> None:
        """P(0; 2.7) ~ 0.067."""
        result = poisson_pmf(0, 2.7)
        assert abs(result - math.exp(-2.7)) < 1e-6
        assert abs(result - 0.0672) < 0.001

    def test_poisson_pmf_k3(self) -> None:
        """P(3; 2.7) ~ 0.22."""
        result = poisson_pmf(3, 2.7)
        expected = (2.7**3) * math.exp(-2.7) / math.factorial(3)
        assert abs(result - expected) < 1e-6
        assert abs(result - 0.2205) < 0.01

    def test_poisson_pmf_negative_k(self) -> None:
        """P(k<0; lam) = 0."""
        assert poisson_pmf(-1, 2.7) == 0.0

    def test_poisson_pmf_zero_lambda(self) -> None:
        """P(k; lam<=0) = 0."""
        assert poisson_pmf(0, 0.0) == 0.0
        assert poisson_pmf(1, -1.0) == 0.0


class TestComputePoissonProbability:
    """Tests for compute_poisson_probability."""

    def test_compute_poisson_probability_soccer(self) -> None:
        """Corridor [2.5, 3.5] for soccer_epl: only k=3 contributes."""
        result = compute_poisson_probability(2.5, 3.5, "soccer_epl")
        # Only k=3 is inside (2.5, 3.5)
        expected = poisson_pmf(3, 2.7)
        assert abs(result - expected) < 1e-6
        assert result > 0.15

    def test_compute_poisson_probability_basketball(self) -> None:
        """Basketball corridor uses normal approximation."""
        result = compute_poisson_probability(215.0, 225.0, "basketball_nba")
        # mean=220.5, std=22.05, corridor [215, 225] is narrow near mean
        assert 0.0 < result < 1.0
        # Should be a reasonable probability for 10 points around mean
        assert result > 0.1

    def test_compute_poisson_probability_unknown_sport(self) -> None:
        """Unknown sport falls back to naive formula."""
        result = compute_poisson_probability(2.0, 4.0, "unknown_sport")
        # Naive: width / corridor_high = 2.0 / 4.0 = 0.5
        assert abs(result - 0.5) < 1e-6


class TestMiddleScanner:
    """Tests for MiddleScanner."""

    def test_find_middles_totals(self) -> None:
        """Finds corridor when Over < Under from different bookmakers."""
        event = {
            "id": "mid1",
            "sport": "soccer_epl",
            "home_team": "A",
            "away_team": "B",
            "commence_time": "2024-01-01T15:00:00Z",
            "bookmakers": [
                {
                    "key": "bk1",
                    "markets": [{"key": "totals", "outcomes": [
                        {"name": "Over", "price": 1.95, "point": 2.5},
                    ]}],
                },
                {
                    "key": "bk2",
                    "markets": [{"key": "totals", "outcomes": [
                        {"name": "Under", "price": 1.90, "point": 3.5},
                    ]}],
                },
            ],
        }
        scanner = MiddleScanner()
        result = scanner.find_middles_totals([event])
        assert len(result) == 1
        opp = result[0]
        assert opp.type == "middle_totals"
        assert opp.middle_range == [2.5, 3.5]
        assert opp.middle_probability > 0.0

    def test_find_middles_totals_same_bk_ignored(self) -> None:
        """Same bookmaker on both legs is not paired."""
        event = {
            "id": "mid2",
            "sport": "soccer_epl",
            "home_team": "C",
            "away_team": "D",
            "commence_time": "2024-01-01T15:00:00Z",
            "bookmakers": [
                {
                    "key": "bk1",
                    "markets": [{"key": "totals", "outcomes": [
                        {"name": "Over", "price": 1.95, "point": 2.5},
                        {"name": "Under", "price": 1.90, "point": 3.5},
                    ]}],
                },
            ],
        }
        scanner = MiddleScanner()
        result = scanner.find_middles_totals([event])
        assert result == []
