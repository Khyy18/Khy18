"""Tests for Telegram chat parser: keyword detection, anti-spam, response generation."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import tg_chat_parser


@pytest.fixture(autouse=True)
def reset_tg_state():
    """Reset module-level state between tests."""
    tg_chat_parser._response_timestamps.clear()
    yield


@pytest.mark.asyncio
class TestTgChatParser:

    async def test_matches_keywords_in_messages(self):
        """_message_matches_keywords detects relevant messages."""
        assert tg_chat_parser._message_matches_keywords("Ищу копирайтера для проекта") is True
        assert tg_chat_parser._message_matches_keywords("нужен текст для сайта") is True
        assert tg_chat_parser._message_matches_keywords("кто напишет статью?") is True
        assert tg_chat_parser._message_matches_keywords("привет, как дела?") is False
        assert tg_chat_parser._message_matches_keywords("") is False
        assert tg_chat_parser._message_matches_keywords(None) is False

    async def test_antispam_blocks_after_limit(self, monkeypatch):
        """After N responses in one hour, should block further responses."""
        monkeypatch.setattr("tg_chat_parser.config.TG_MAX_RESPONSES_PER_HOUR", 3)
        chat_id = 12345

        # First 3 responses should be allowed
        assert tg_chat_parser._can_respond_in_chat(chat_id) is True
        tg_chat_parser._record_response(chat_id)

        assert tg_chat_parser._can_respond_in_chat(chat_id) is True
        tg_chat_parser._record_response(chat_id)

        assert tg_chat_parser._can_respond_in_chat(chat_id) is True
        tg_chat_parser._record_response(chat_id)

        # 4th response should be blocked
        assert tg_chat_parser._can_respond_in_chat(chat_id) is False

    async def test_generate_chat_response_returns_text(self, monkeypatch):
        """generate_contextual_response returns text via mocked LLM."""
        monkeypatch.setattr(tg_chat_parser, "_llm_router", None)
        monkeypatch.setattr("tg_chat_parser.config.OPENAI_API_KEY", "test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Могу помочь, пишите в ЛС!"

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Reset the singleton
        tg_chat_parser._openai_client = mock_client

        result = await tg_chat_parser.generate_contextual_response("Ищу копирайтера")

        assert result == "Могу помочь, пишите в ЛС!"

    async def test_old_timestamps_cleaned(self, monkeypatch):
        """Old response timestamps (>1 hour) are cleaned up."""
        monkeypatch.setattr("tg_chat_parser.config.TG_MAX_RESPONSES_PER_HOUR", 3)
        chat_id = 99999

        # Add old timestamps (2 hours ago)
        old_time = time.time() - 7200
        tg_chat_parser._response_timestamps[chat_id] = [old_time, old_time, old_time]

        # Should be allowed since old timestamps get cleaned
        assert tg_chat_parser._can_respond_in_chat(chat_id) is True
