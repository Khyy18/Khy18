"""Tests for CashoutEngine from arbitrage.cashout."""

from __future__ import annotations

from arbitrage.cashout import CashoutEngine


class TestCashoutEngine:
    """Tests for CashoutEngine."""

    def test_calculate_cashout_profit_positive(self) -> None:
        """Odds dropped (profit): original higher than current."""
        engine = CashoutEngine()
        # Original odds 3.0, current odds 2.0, stake 100
        # profit = 100 * (3.0/2.0 - 1) = 100 * 0.5 = 50
        profit = engine.calculate_cashout_profit(3.0, 2.0, 100.0)
        assert abs(profit - 50.0) < 0.01

    def test_calculate_cashout_profit_negative(self) -> None:
        """Odds rose (loss): current higher than original."""
        engine = CashoutEngine()
        # Original odds 2.0, current odds 3.0, stake 100
        # profit = 100 * (2.0/3.0 - 1) = 100 * (-0.333) = -33.33
        profit = engine.calculate_cashout_profit(2.0, 3.0, 100.0)
        assert profit < 0
        assert abs(profit - (-33.33)) < 0.01

    def test_calculate_cashout_profit_edge_cases(self) -> None:
        """odds <= 1, stake <= 0 returns 0."""
        engine = CashoutEngine()
        assert engine.calculate_cashout_profit(0.5, 2.0, 100.0) == 0.0
        assert engine.calculate_cashout_profit(2.0, 0.8, 100.0) == 0.0
        assert engine.calculate_cashout_profit(2.0, 2.0, 0.0) == 0.0
        assert engine.calculate_cashout_profit(2.0, 2.0, -10.0) == 0.0

    def test_find_cashout_opportunities(self) -> None:
        """Matches bet to current event and finds cashout opportunity."""
        engine = CashoutEngine()
        pre_match_bets = [
            {
                "event_id": "e1",
                "event_name": "A vs B",
                "bookmaker": "pinnacle",
                "outcome": "A",
                "odds": 3.0,
                "stake": 100.0,
                "placed_ts": "2024-01-01T12:00:00Z",
            }
        ]
        current_events = [
            {
                "id": "e1",
                "sport": "soccer_epl",
                "home_team": "A",
                "away_team": "B",
                "bookmakers": [
                    {
                        "key": "pinnacle",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "A", "price": 2.0},
                            {"name": "B", "price": 3.5},
                        ]}],
                    }
                ],
            }
        ]
        result = engine.find_cashout_opportunities(pre_match_bets, current_events)
        assert len(result) == 1
        opp = result[0]
        assert opp.cashout_profit_pct > 0
        assert opp.recommendation in ("cashout", "partial_cashout", "hold")
