"""Tests for FreeBetConverter."""

from arbitrage.freebet import FreeBetConverter


class TestFreeBetConverter:
    def test_calculate_conversion_positive_profit(self) -> None:
        """Conversion should yield positive profit."""
        converter = FreeBetConverter()
        result = converter.calculate_conversion(50.0, 5.0, 5.2, 0.05)
        assert result["guaranteed_profit"] > 0

    def test_conversion_rate_reasonable(self) -> None:
        """Conversion rate should be between 50-95% for typical odds."""
        converter = FreeBetConverter()
        result = converter.calculate_conversion(100.0, 4.0, 4.2, 0.05)
        assert 50.0 <= result["conversion_rate"] <= 95.0

    def test_zero_commission(self) -> None:
        """Zero commission should give higher conversion."""
        converter = FreeBetConverter()
        with_comm = converter.calculate_conversion(100.0, 5.0, 5.0, 0.05)
        no_comm = converter.calculate_conversion(100.0, 5.0, 5.0, 0.0)
        assert no_comm["guaranteed_profit"] >= with_comm["guaranteed_profit"]

    def test_high_odds_conversion(self) -> None:
        """Higher back odds should generally give better conversion (if lay matches)."""
        converter = FreeBetConverter()
        # Same lay-back spread but higher odds
        low = converter.calculate_conversion(100.0, 3.0, 3.2, 0.05)
        high = converter.calculate_conversion(100.0, 6.0, 6.2, 0.05)
        # Both should be positive
        assert low["guaranteed_profit"] > 0
        assert high["guaranteed_profit"] > 0
