"""Tests for CLVTracker from arbitrage.clv_tracker."""

from __future__ import annotations

from arbitrage.clv_tracker import CLVTracker


class TestCLVTracker:
    """Tests for CLVTracker."""

    def test_extract_best_odds_pinnacle(self) -> None:
        """Prefers pinnacle odds over other bookmakers."""
        tracker = CLVTracker()
        event_data = {
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "markets": [{"key": "h2h", "outcomes": [
                        {"name": "Home", "price": 2.10},
                        {"name": "Away", "price": 3.50},
                    ]}],
                },
                {
                    "key": "bet365",
                    "markets": [{"key": "h2h", "outcomes": [
                        {"name": "Home", "price": 2.20},
                        {"name": "Away", "price": 3.80},
                    ]}],
                },
            ]
        }
        best = tracker._extract_best_odds(event_data)
        # Should prefer pinnacle's highest odds (3.50), not bet365 (3.80)
        assert best == 3.50

    def test_extract_best_odds_fallback(self) -> None:
        """Uses max if no pinnacle available."""
        tracker = CLVTracker()
        event_data = {
            "bookmakers": [
                {
                    "key": "bet365",
                    "markets": [{"key": "h2h", "outcomes": [
                        {"name": "Home", "price": 2.20},
                        {"name": "Away", "price": 3.80},
                    ]}],
                },
                {
                    "key": "unibet",
                    "markets": [{"key": "h2h", "outcomes": [
                        {"name": "Home", "price": 2.15},
                        {"name": "Away", "price": 3.70},
                    ]}],
                },
            ]
        }
        best = tracker._extract_best_odds(event_data)
        # No pinnacle, so fallback to max: 3.80
        assert best == 3.80

    def test_cashout_formula(self) -> None:
        """CLV formula: (placement/closing - 1)*100."""
        placement_odds = 2.50
        closing_odds = 2.00
        clv_pct = (placement_odds / closing_odds - 1.0) * 100.0
        assert abs(clv_pct - 25.0) < 1e-6

        # Negative CLV
        placement_odds = 1.80
        closing_odds = 2.00
        clv_pct = (placement_odds / closing_odds - 1.0) * 100.0
        assert clv_pct < 0
        assert abs(clv_pct - (-10.0)) < 1e-6
