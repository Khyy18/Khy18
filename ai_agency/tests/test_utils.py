"""Tests for utils module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import format_number, progress_bar, status_indicator, sparkline, _card, THIN_SPACE


class TestFormatNumber:
    """Test format_number() function."""

    def test_integer(self):
        """Formats integer with thin space separator."""
        result = format_number(10000)
        assert result == f"10{THIN_SPACE}000"

    def test_float(self):
        """Formats float with thin space separator and decimal."""
        result = format_number(1234567.89)
        assert f"1{THIN_SPACE}234{THIN_SPACE}567.89" == result

    def test_small_number(self):
        """Small number without separator."""
        result = format_number(100)
        assert result == "100"


class TestProgressBar:
    """Test progress_bar() function."""

    def test_zero_percent(self):
        """Progress bar at 0%."""
        result = progress_bar(0, 10)
        assert "0%" in result
        assert "\u2588" not in result  # No filled blocks

    def test_fifty_percent(self):
        """Progress bar at 50%."""
        result = progress_bar(5, 10)
        assert "50%" in result

    def test_hundred_percent(self):
        """Progress bar at 100%."""
        result = progress_bar(10, 10)
        assert "100%" in result
        assert "\u2591" not in result  # No empty blocks


class TestStatusIndicator:
    """Test status_indicator() function."""

    def test_completed_status(self):
        """Returns green circle for completed."""
        result = status_indicator("completed")
        assert result == "\U0001f7e2"

    def test_processing_status(self):
        """Returns yellow circle for processing."""
        result = status_indicator("processing")
        assert result == "\U0001f7e1"

    def test_failed_status(self):
        """Returns red circle for failed."""
        result = status_indicator("failed")
        assert result == "\U0001f534"

    def test_pending_status(self):
        """Returns white circle for pending."""
        result = status_indicator("pending")
        assert result == "\u26aa"

    def test_unknown_status(self):
        """Returns white circle for unknown status."""
        result = status_indicator("unknown")
        assert result == "\u26aa"


class TestSparkline:
    """Test sparkline() function."""

    def test_correct_length(self):
        """Sparkline produces output of correct length."""
        values = [1, 2, 3, 4, 5]
        result = sparkline(values)
        assert len(result) == 5

    def test_empty_values(self):
        """Sparkline returns empty string for empty list."""
        result = sparkline([])
        assert result == ""

    def test_constant_values(self):
        """Sparkline with constant values uses middle char."""
        result = sparkline([5, 5, 5])
        assert len(result) == 3


class TestCard:
    """Test _card() function."""

    def test_formats_with_title_emoji_body(self):
        """Card formats correctly with title, emoji, and body lines."""
        result = _card("Title", "\U0001f4cb", ["line1", "line2"])
        assert "\U0001f4cb" in result
        assert "<b>Title</b>" in result
        assert "line1" in result
        assert "line2" in result
