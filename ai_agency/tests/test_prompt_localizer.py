"""Tests for prompt_localizer module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
class TestPromptLocalizer:
    """Test prompt_localizer module functionality."""

    async def test_ru_passthrough(self, initialized_db):
        """Russian language returns original prompts without translation."""
        import prompt_localizer
        system, user = await prompt_localizer.get_localized_prompts("copywriting", "ru")
        assert system != ""
        assert user != ""
        assert "{input_text}" in user

    async def test_cache_hit(self, initialized_db):
        """Second call for same service+lang returns from cache."""
        import prompt_localizer

        # Clear cache first
        prompt_localizer.clear_cache()

        # Mock the translate function to track calls
        call_count = {"count": 0}

        async def mock_translate(text, lang):
            call_count["count"] += 1
            return f"[EN] {text}"

        with patch.object(prompt_localizer, "_translate_prompt", side_effect=mock_translate):
            # First call - translates
            s1, u1 = await prompt_localizer.get_localized_prompts("copywriting", "en")
            first_count = call_count["count"]

            # Second call - from cache
            s2, u2 = await prompt_localizer.get_localized_prompts("copywriting", "en")
            assert call_count["count"] == first_count  # No additional calls
            assert s1 == s2
            assert u1 == u2

        prompt_localizer.clear_cache()

    async def test_clear_cache(self, initialized_db):
        """clear_cache removes all cached entries."""
        import prompt_localizer
        prompt_localizer._prompt_cache[("test", "en")] = ("sys", "usr")
        prompt_localizer.clear_cache()
        assert len(prompt_localizer._prompt_cache) == 0

    async def test_invalid_service_type(self, initialized_db):
        """Invalid service type returns empty strings."""
        import prompt_localizer
        prompt_localizer.clear_cache()
        system, user = await prompt_localizer.get_localized_prompts("nonexistent", "en")
        assert system == ""
        assert user == ""
