"""Tests for voice_handler module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import voice_handler


@pytest.mark.asyncio
class TestVoiceHandler:
    """Tests for voice order processing."""

    async def test_transcribe_audio_success(self):
        """transcribe_audio returns transcribed text on success."""
        mock_response = MagicMock()
        mock_response.text = "Hello world"

        with patch.object(voice_handler, "_openai_client", None):
            mock_client = AsyncMock()
            mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)
            with patch("voice_handler._get_openai_client", return_value=mock_client):
                result = await voice_handler.transcribe_audio(b"fake_audio_data")
                assert result == "Hello world"

    async def test_transcribe_audio_failure(self):
        """transcribe_audio returns None on API error."""
        with patch.object(voice_handler, "_openai_client", None):
            mock_client = AsyncMock()
            mock_client.audio.transcriptions.create = AsyncMock(
                side_effect=Exception("API error")
            )
            with patch("voice_handler._get_openai_client", return_value=mock_client):
                result = await voice_handler.transcribe_audio(b"fake_audio_data")
                assert result is None

    async def test_handle_voice_no_voice(self):
        """handle_voice returns ENTER_TEXT when no voice in message."""
        update = MagicMock()
        update.message.voice = None
        update.message.audio = None
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        result = await voice_handler.handle_voice(update, context)
        assert result == voice_handler.ENTER_TEXT

    async def test_handle_voice_confirmation_cancel(self):
        """handle_voice_confirmation clears data on cancel."""
        update = MagicMock()
        update.callback_query.data = "voice_cancel"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()

        context = MagicMock()
        context.user_data = {"voice_transcription": "test text"}

        result = await voice_handler.handle_voice_confirmation(update, context)
        assert result == voice_handler.ENTER_TEXT
        assert "voice_transcription" not in context.user_data

    async def test_handle_voice_confirmation_confirm(self):
        """handle_voice_confirmation sets input_text on confirm."""
        update = MagicMock()
        update.callback_query.data = "voice_confirm"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()

        context = MagicMock()
        context.user_data = {"voice_transcription": "transcribed text"}

        result = await voice_handler.handle_voice_confirmation(update, context)
        assert result == voice_handler.ENTER_TEXT
        assert context.user_data.get("input_text") == "transcribed text"
