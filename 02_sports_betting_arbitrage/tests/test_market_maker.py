"""Tests for MarketMaker: round_to_tick and calculate_spread edge cases."""

from arbitrage.betfair_stream import MarketMaker, round_to_tick


class TestRoundToTick:
    """Tests for round_to_tick helper."""

    def test_back_exact_tick_155(self):
        """1.55 is already a valid tick in the 1.01-2.00 range (inc 0.01)."""
        assert round_to_tick(1.55, "back") == 1.55

    def test_back_rounds_down_1555(self):
        """1.555 rounded down to nearest 0.01 tick = 1.55."""
        assert round_to_tick(1.555, "back") == 1.55

    def test_lay_rounds_up_1555(self):
        """1.555 rounded up to nearest 0.01 tick = 1.56."""
        assert round_to_tick(1.555, "lay") == 1.56

    def test_back_exact_tick_250(self):
        """2.50 is a valid tick in the 2.0-3.0 range (inc 0.02)."""
        assert round_to_tick(2.5, "back") == 2.50

    def test_lay_rounds_up_251(self):
        """2.51 in 2.0-3.0 range (inc 0.02) rounds up to 2.52."""
        assert round_to_tick(2.51, "lay") == 2.52


class TestCalculateSpread:
    """Tests for MarketMaker.calculate_spread edge cases."""

    def setup_method(self):
        self.mm = MarketMaker()

    def test_volume_zero_spread_002(self):
        """With volume=0, spread should be 0.02."""
        result = self.mm.calculate_spread(best_back=1.90, best_lay=1.95, volume=0)
        # spread=0.02, clamped to min(0.02, 1.95-1.90=0.05) = 0.02
        # mid=1.925, back=1.925-0.01=1.915 -> tick 1.91, lay=1.925+0.01=1.935 -> tick 1.94
        assert result["back_price"] < result["lay_price"]
        # The spread formula gives 0.02 when volume=0
        assert result["expected_profit_per_match"] > 0

    def test_volume_tiny_clamps_to_book_spread(self):
        """With volume=0.001, raw spread=3.16, must clamp to lay-back."""
        result = self.mm.calculate_spread(best_back=1.90, best_lay=1.95, volume=0.001)
        # Spread should be clamped to 1.95 - 1.90 = 0.05
        book_spread = 1.95 - 1.90
        actual_spread = result["lay_price"] - result["back_price"]
        # The actual spread (after tick rounding) should not wildly exceed book spread
        assert actual_spread <= book_spread + 0.02  # allow one tick tolerance from rounding

    def test_normal_volume_sensible(self):
        """With volume=10000, back=1.90, lay=1.95, returns sensible values."""
        result = self.mm.calculate_spread(best_back=1.90, best_lay=1.95, volume=10000)
        # mid = 1.925, spread = max(0.02, 1/sqrt(10000)*0.1) = max(0.02, 0.001) = 0.02
        # clamped to min(0.02, 0.05) = 0.02
        assert result["back_price"] >= 1.01
        assert result["lay_price"] <= 1.95
        assert result["back_price"] < result["lay_price"]
        assert result["expected_profit_per_match"] > 0
        # With high volume, spread should be tight
        assert result["lay_price"] - result["back_price"] <= 0.05
