import pytest

from kindergarten_accountant_bot.utils.formatting import (
    _card,
    format_money,
    progress_bar,
    status_indicator,
)


class TestCard:
    def test_card_produces_html_pre(self):
        result = _card("Test", "X", ["line1", "line2"])
        assert result.startswith("<pre>")
        assert result.endswith("</pre>")

    def test_card_contains_title_and_emoji(self):
        result = _card("Title", "E", ["body"])
        assert "E Title" in result

    def test_card_contains_separator(self):
        result = _card("T", "X", ["body"])
        separator = "\u2501" * 24
        assert separator in result

    def test_card_contains_body_lines(self):
        result = _card("T", "X", ["line1", "line2"])
        assert "line1" in result
        assert "line2" in result


class TestFormatMoney:
    def test_format_1000(self):
        result = format_money(1000)
        assert result == "1\u202f000.00 \u20bd"

    def test_format_1000000(self):
        result = format_money(1000000)
        assert result == "1\u202f000\u202f000.00 \u20bd"

    def test_format_0_5(self):
        result = format_money(0.5)
        assert result == "0.50 \u20bd"

    def test_format_45000(self):
        result = format_money(45000)
        assert result == "45\u202f000.00 \u20bd"


class TestProgressBar:
    def test_empty_bar(self):
        result = progress_bar(0, 10)
        assert result == "\u25b1" * 10

    def test_full_bar(self):
        result = progress_bar(10, 10)
        assert result == "\u25b0" * 10

    def test_half_bar(self):
        result = progress_bar(5, 10)
        assert result == "\u25b0" * 5 + "\u25b1" * 5

    def test_custom_length(self):
        result = progress_bar(5, 10, length=20)
        assert result == "\u25b0" * 10 + "\u25b1" * 10

    def test_zero_total(self):
        result = progress_bar(0, 0)
        assert result == "\u25b1" * 10


class TestStatusIndicator:
    def test_good(self):
        assert status_indicator("good") == "\u2705"

    def test_warning(self):
        assert status_indicator("warning") == "\u26a0\ufe0f"

    def test_bad(self):
        assert status_indicator("bad") == "\u274c"

    def test_neutral(self):
        assert status_indicator("neutral") == "\u2796"

    def test_unknown_returns_neutral(self):
        assert status_indicator("unknown") == "\u2796"
