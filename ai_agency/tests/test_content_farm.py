"""Tests for content_farm module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import content_farm


@pytest.mark.asyncio
class TestContentFarm:
    """Tests for auto content generation."""

    async def test_parse_channels_empty(self, mock_config):
        """_parse_channels returns empty list when no config."""
        channels = content_farm._parse_channels()
        assert channels == []

    async def test_parse_channels_valid(self, monkeypatch):
        """_parse_channels parses valid JSON config."""
        import config
        monkeypatch.setattr(
            config, "CONTENT_FARM_CHANNELS",
            '[{"channel_id": "@test", "niche": "ai_news"}]'
        )
        channels = content_farm._parse_channels()
        assert len(channels) == 1
        assert channels[0]["channel_id"] == "@test"

    async def test_generate_post_success(self):
        """generate_post returns generated text."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Great business tip post"

        with patch.object(content_farm, "_openai_client", None):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            with patch("content_farm._get_openai_client", return_value=mock_client):
                result = await content_farm.generate_post("business_tips")
                assert result is not None
                assert "Great business tip post" in result

    async def test_generate_post_unknown_niche(self):
        """generate_post returns None for unknown niche."""
        result = await content_farm.generate_post("unknown_niche")
        assert result is None

    async def test_generate_post_failure(self):
        """generate_post returns None on API error."""
        with patch.object(content_farm, "_openai_client", None):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=Exception("API error")
            )
            with patch("content_farm._get_openai_client", return_value=mock_client):
                result = await content_farm.generate_post("ai_news")
                assert result is None

    async def test_check_and_post_no_bot(self):
        """check_and_post returns 0 when no bot provided."""
        result = await content_farm.check_and_post(bot=None)
        assert result == 0

    async def test_niches_defined(self):
        """All expected niches are defined."""
        expected = {"business_tips", "marketing", "ai_news", "copywriting_hacks"}
        assert set(content_farm.NICHES.keys()) == expected
