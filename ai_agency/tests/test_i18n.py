"""Tests for i18n module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from i18n import get_text


class TestGetText:
    """Test i18n.get_text() function."""

    def test_ru_text_for_ru_key(self):
        """Returns Russian text for RU language key."""
        text = get_text("ru", "welcome", name="Тест")
        assert "Привет" in text
        assert "Тест" in text

    def test_en_text_for_en_key(self):
        """Returns English text for EN language key."""
        text = get_text("en", "welcome", name="Test")
        assert "Hello" in text
        assert "Test" in text

    def test_format_kwargs(self):
        """Formats text with kwargs correctly."""
        text = get_text("ru", "balance", amount="1000")
        assert "1000" in text

    def test_fallback_to_ru_if_en_missing(self):
        """Falls back to RU if a key is not available in the requested language."""
        # Use a key that exists - get_text should return the RU version
        # for a non-existent language
        text = get_text("fr", "welcome", name="Pierre")
        # Should fallback to RU version
        assert "Привет" in text
        assert "Pierre" in text

    def test_returns_key_if_not_found(self):
        """Returns the key itself if not found in any language."""
        text = get_text("ru", "totally_nonexistent_key_xyz")
        assert text == "totally_nonexistent_key_xyz"

    def test_text_without_kwargs(self):
        """Returns text without formatting when no kwargs provided."""
        text = get_text("ru", "confirm_order")
        assert text == "Подтвердите заказ:"
