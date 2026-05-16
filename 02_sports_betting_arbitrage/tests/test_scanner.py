"""Tests for ArbitrageScanner from arbitrage.scanner."""

from __future__ import annotations

from arbitrage.scanner import ArbitrageScanner


class TestFindSurebets:
    """Tests for find_surebets method."""

    def test_find_surebets_detects_arb(self, sample_surebet_event: dict) -> None:
        """Event with inverse_sum < 1.0 should be detected as arb."""
        scanner = ArbitrageScanner(min_arb_profit=0.1)
        events = [sample_surebet_event]
        result = scanner.find_surebets(events)
        assert len(result) >= 1
        assert result[0].type == "surebet"
        assert result[0].profit_pct > 0.0

    def test_find_surebets_no_arb(self, mock_event: dict) -> None:
        """Event with inverse_sum >= 1.0 returns empty."""
        scanner = ArbitrageScanner(min_arb_profit=0.1)
        events = [mock_event]
        result = scanner.find_surebets(events)
        assert result == []

    def test_find_surebets_respects_min_profit(self) -> None:
        """Arb with profit below MIN_ARB_PROFIT is skipped."""
        # Construct event with a very small arb (~0.5% profit)
        event = {
            "id": "low_arb",
            "sport": "soccer_epl",
            "home_team": "A",
            "away_team": "B",
            "commence_time": "2024-01-01T15:00:00Z",
            "bookmakers": [
                {
                    "key": "bk1",
                    "markets": [{"key": "h2h", "outcomes": [
                        {"name": "A", "price": 2.05},
                        {"name": "B", "price": 2.05},
                    ]}],
                },
                {
                    "key": "bk2",
                    "markets": [{"key": "h2h", "outcomes": [
                        {"name": "A", "price": 2.04},
                        {"name": "B", "price": 2.04},
                    ]}],
                },
            ],
        }
        # inverse_sum = 1/2.05 + 1/2.05 ~ 0.976 -> profit ~2.5%
        # Set min_profit very high so it's skipped
        scanner = ArbitrageScanner(min_arb_profit=5.0)
        result = scanner.find_surebets([event])
        assert result == []

    def test_find_surebets_totals(self) -> None:
        """Over/under lines creating arb should be detected."""
        event = {
            "id": "totals_arb",
            "sport": "soccer_epl",
            "home_team": "X",
            "away_team": "Y",
            "commence_time": "2024-01-01T15:00:00Z",
            "bookmakers": [
                {
                    "key": "bk1",
                    "markets": [{"key": "totals", "outcomes": [
                        {"name": "Over", "price": 2.20, "point": 2.5},
                        {"name": "Under", "price": 1.70, "point": 2.5},
                    ]}],
                },
                {
                    "key": "bk2",
                    "markets": [{"key": "totals", "outcomes": [
                        {"name": "Over", "price": 1.80, "point": 2.5},
                        {"name": "Under", "price": 2.15, "point": 2.5},
                    ]}],
                },
            ],
        }
        # Best Over = 2.20 (bk1), Best Under = 2.15 (bk2)
        # inverse_sum = 1/2.20 + 1/2.15 ~ 0.4545 + 0.4651 = 0.9196 < 1
        scanner = ArbitrageScanner(min_arb_profit=0.1)
        result = scanner.find_surebets_totals([event])
        assert len(result) >= 1
        assert result[0].type == "surebet_totals"

    def test_find_surebets_spreads(self) -> None:
        """Spread lines creating arb should be detected."""
        event = {
            "id": "spreads_arb",
            "sport": "basketball_nba",
            "home_team": "TeamH",
            "away_team": "TeamA",
            "commence_time": "2024-01-01T19:00:00Z",
            "bookmakers": [
                {
                    "key": "bk1",
                    "markets": [{"key": "spreads", "outcomes": [
                        {"name": "TeamH", "price": 2.10, "point": -3.5},
                        {"name": "TeamA", "price": 1.85, "point": 3.5},
                    ]}],
                },
                {
                    "key": "bk2",
                    "markets": [{"key": "spreads", "outcomes": [
                        {"name": "TeamH", "price": 1.90, "point": -3.5},
                        {"name": "TeamA", "price": 2.05, "point": 3.5},
                    ]}],
                },
            ],
        }
        # Best TeamH = 2.10, Best TeamA = 2.05
        # inverse_sum = 1/2.10 + 1/2.05 ~ 0.476 + 0.488 = 0.964 < 1
        scanner = ArbitrageScanner(min_arb_profit=0.1)
        result = scanner.find_surebets_spreads([event])
        assert len(result) >= 1
        assert result[0].type == "surebet_spreads"

    def test_extract_h2h_outcomes(self, mock_event: dict) -> None:
        """Correctly parses bookmaker structure for h2h outcomes."""
        result = ArbitrageScanner._extract_h2h_outcomes(mock_event)
        assert "Arsenal" in result
        assert "Chelsea" in result
        assert "Draw" in result
        # Each outcome should have offers from both bookmakers
        assert len(result["Arsenal"]) == 2
        # Check format: list of (odds, bookmaker_key)
        assert result["Arsenal"][0][1] in ("pinnacle", "bet365")

    def test_find_surebets_empty_events(self) -> None:
        """Empty events list returns empty."""
        scanner = ArbitrageScanner()
        assert scanner.find_surebets([]) == []

    def test_find_value_bets_detects_edge(self, sample_value_event: dict) -> None:
        """Value bet with edge >= 3% should be found."""
        scanner = ArbitrageScanner(min_value_edge=3.0)
        # sharp_probs: Pinnacle odds 2.0/3.0/4.0 -> probs ~0.5/0.333/0.25
        sharp_probs = {"val_evt": [0.55, 0.35, 0.25]}
        # bet365 odds 2.50: edge = (2.50 * 0.55 - 1)*100 = 37.5%
        result = scanner.find_value_bets([sample_value_event], sharp_probs)
        assert len(result) >= 1
        assert result[0].type == "value_bet"
        assert result[0].edge_pct >= 3.0

    def test_find_value_bets_ignores_small_edge(self, sample_value_event: dict) -> None:
        """Value bet with edge < min_value_edge is skipped."""
        scanner = ArbitrageScanner(min_value_edge=3.0)
        # Probs that yield negative or very small edge at bet365 odds
        # bet365 offers 2.50/3.20/4.10
        # If true prob for outcome is 0.38, edge = (2.50*0.38 - 1)*100 = -5% (negative)
        sharp_probs = {"val_evt": [0.38, 0.30, 0.22]}
        result = scanner.find_value_bets([sample_value_event], sharp_probs)
        assert result == []
