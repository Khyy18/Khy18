"""Tests for DutchingEngine."""

from arbitrage.dutching import DutchingEngine


class TestDutchingEngine:
    def test_calculate_dutch_stakes_equal_return(self) -> None:
        """All outcomes should produce the same return."""
        engine = DutchingEngine()
        odds = [2.0, 3.0, 6.0]
        stakes = engine.calculate_dutch_stakes(odds, 100.0)
        # return = stake_i * odds_i should be equal for all
        returns = [s * o for s, o in zip(stakes, odds)]
        assert len(set(round(r, 2) for r in returns)) == 1

    def test_calculate_dutch_stakes_single_outcome(self) -> None:
        """Single outcome: entire stake on it."""
        engine = DutchingEngine()
        odds = [3.0]
        stakes = engine.calculate_dutch_stakes(odds, 100.0)
        assert len(stakes) == 1
        assert abs(stakes[0] - 100.0) < 0.01

    def test_dutch_stakes_sum_equals_total(self) -> None:
        """Stakes should sum to total_stake."""
        engine = DutchingEngine()
        odds = [2.0, 3.0, 6.0]
        stakes = engine.calculate_dutch_stakes(odds, 100.0)
        assert abs(sum(stakes) - 100.0) < 0.01

    def test_find_dutching_low_overround(self) -> None:
        """Event with very low overround should be detected."""
        engine = DutchingEngine(max_overround=0.05)
        # Odds: 1/2.0 + 1/2.0 = 1.0 (exactly fair, overround=0)
        events = [{
            "sport": "soccer_epl",
            "home_team": "A",
            "away_team": "B",
            "bookmakers": [{
                "key": "testbk",
                "markets": [{"key": "h2h", "outcomes": [
                    {"name": "A", "price": 2.0},
                    {"name": "B", "price": 2.0},
                ]}],
            }],
        }]
        opps = engine.find_dutching_opportunities(events)
        assert len(opps) >= 1
        assert opps[0].profit_pct >= 0.0
