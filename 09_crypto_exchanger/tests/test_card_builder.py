"""Tests for card builder formatting utilities."""

import pytest

from bot.card_builder import (
    _card,
    format_number,
    progress_bar,
    status_icon,
    SEPARATOR,
    BAR_FILLED,
    BAR_EMPTY,
    STATUS_ICONS,
    exchange_card,
    status_card,
    error_card,
    welcome_card,
)


class TestFormatNumber:
    """Test number formatting with thin non-breaking spaces."""

    def test_zero(self):
        """Test formatting zero."""
        assert format_number(0) == "0"

    def test_small_number(self):
        """Test small numbers without thousands separator."""
        result = format_number(123.456)
        assert "123.456" in result
        # No thin space for numbers < 1000
        assert "\u202f" not in result

    def test_large_number_has_thin_space(self):
        """Test large numbers get thin non-breaking space as thousands separator."""
        result = format_number(1234567.89)
        assert "\u202f" in result
        # Should have proper grouping
        assert "1\u202f234\u202f567.89" == result

    def test_trailing_zeros_removed(self):
        """Test that trailing zeros after decimal are removed."""
        result = format_number(1.50000000)
        assert result == "1.5"

    def test_whole_number_no_decimal(self):
        """Test that whole numbers don't show decimal point."""
        result = format_number(100.0)
        assert "." not in result
        assert result == "100"

    def test_custom_decimals(self):
        """Test formatting with custom decimal places."""
        result = format_number(1234.5678, decimals=2)
        assert "1\u202f234.57" == result

    def test_very_small_number(self):
        """Test formatting very small crypto amounts."""
        result = format_number(0.00000001)
        assert result == "0.00000001"


class TestProgressBar:
    """Test progress bar generation."""

    def test_zero_progress(self):
        """Test empty progress bar."""
        result = progress_bar(0)
        assert result == BAR_EMPTY * 10
        assert len(result) == 10

    def test_full_progress(self):
        """Test full progress bar."""
        result = progress_bar(10)
        assert result == BAR_FILLED * 10
        assert len(result) == 10

    def test_partial_progress(self):
        """Test partial progress bar."""
        result = progress_bar(5)
        assert result == BAR_FILLED * 5 + BAR_EMPTY * 5
        assert len(result) == 10

    def test_overflow_capped_at_total(self):
        """Test that values > total are capped."""
        result = progress_bar(15, total=10)
        assert result == BAR_FILLED * 10
        assert len(result) == 10

    def test_custom_total(self):
        """Test progress bar with custom total."""
        result = progress_bar(3, total=5)
        assert result == BAR_FILLED * 3 + BAR_EMPTY * 2
        assert len(result) == 5


class TestStatusIcon:
    """Test status emoji indicators."""

    def test_known_statuses(self):
        """Test that all known statuses have icons."""
        for status_name in ["new", "waiting", "confirming", "exchanging",
                           "sending", "finished", "failed", "refunded"]:
            icon = status_icon(status_name)
            assert icon == STATUS_ICONS[status_name]
            assert len(icon) > 0

    def test_unknown_status(self):
        """Test that unknown status returns black circle."""
        icon = status_icon("nonexistent_status")
        assert icon == STATUS_ICONS["unknown"]

    def test_case_insensitive(self):
        """Test that status lookup is case-insensitive."""
        assert status_icon("FINISHED") == STATUS_ICONS["finished"]
        assert status_icon("Waiting") == STATUS_ICONS["waiting"]


class TestCard:
    """Test the unified _card() builder."""

    def test_basic_card_structure(self):
        """Test that card has correct HTML structure."""
        result = _card("Test Title", "\U0001f4a1", ["Line 1", "Line 2"])

        assert "<b>Test Title</b>" in result
        assert "\U0001f4a1" in result
        assert "<pre>" in result
        assert "</pre>" in result
        assert SEPARATOR in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_card_with_footer(self):
        """Test card includes footer when provided."""
        result = _card("Title", "\u2705", ["Body"], footer="Footer text")
        assert "Footer text" in result

    def test_card_without_footer(self):
        """Test card without footer does not have extra newline."""
        result = _card("Title", "\u2705", ["Body"])
        lines = result.strip().split("\n")
        # Last line should be the closing </pre> with separator
        assert lines[-1].strip().endswith("</pre>")

    def test_card_preserves_body_lines(self):
        """Test that all body lines appear in order."""
        body = ["First", "Second", "Third"]
        result = _card("T", "E", body)
        idx_first = result.index("First")
        idx_second = result.index("Second")
        idx_third = result.index("Third")
        assert idx_first < idx_second < idx_third


class TestExchangeCard:
    """Test exchange estimate card output."""

    def test_exchange_card_contains_all_info(self):
        """Test exchange card has all required fields."""
        result = exchange_card("btc", "eth", 1.0, 15.5, "changenow", "standard")

        assert "BTC" in result
        assert "ETH" in result
        assert "Changenow" in result
        assert "Float" in result  # standard = Float label
        assert "Exchange Estimate" in result

    def test_exchange_card_fixed_rate_label(self):
        """Test fixed-rate label appears correctly."""
        result = exchange_card("btc", "eth", 1.0, 15.5, "exolix", "fixed-rate")
        assert "Fixed" in result


class TestStatusCard:
    """Test exchange status card output."""

    def test_status_card_includes_progress_bar(self):
        """Test status card includes a progress bar."""
        result = status_card("exc-123", "btc", "eth", 1.0, 15.0, "exchanging")

        assert BAR_FILLED in result
        assert "exc-123" in result
        assert "BTC" in result
        assert "ETH" in result
        assert "Exchanging" in result


class TestErrorCard:
    """Test error card output."""

    def test_error_card_shows_message(self):
        """Test error card displays the error message."""
        result = error_card("Something went wrong")
        assert "Something went wrong" in result
        assert "Error" in result
        assert "\u274c" in result


class TestWelcomeCard:
    """Test welcome card output."""

    def test_welcome_card_structure(self):
        """Test welcome card has essential content."""
        result = welcome_card()
        assert "Crypto Exchanger" in result
        assert "/exchange" in result
        assert "/status" in result
        assert "/help" in result
