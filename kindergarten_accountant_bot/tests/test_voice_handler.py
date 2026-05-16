"""Tests for voice handler - voice message transcription and AI routing."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from kindergarten_accountant_bot.handlers.voice_handler import voice_message_handler


def _make_voice_update_and_context():
    """Create mock Update and Context for voice message."""
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.voice = MagicMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345

    # Mock file download
    mock_file = MagicMock()
    mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"fake_ogg_data"))
    update.message.voice.get_file = AsyncMock(return_value=mock_file)

    context = MagicMock()
    context.user_data = {}
    return update, context


class TestVoiceHandler:
    @pytest.mark.asyncio
    @patch("kindergarten_accountant_bot.handlers.voice_handler.GROQ_API_KEY", "")
    async def test_no_api_key_returns_error(self):
        """Handler replies with error when GROQ_API_KEY is not set."""
        update, context = _make_voice_update_and_context()

        await voice_message_handler(update, context)

        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "не настроены" in call_args[0][0]

    @pytest.mark.asyncio
    @patch("kindergarten_accountant_bot.handlers.voice_handler.GROQ_API_KEY", "test-key")
    @patch("kindergarten_accountant_bot.handlers.voice_handler._call_ai_backend")
    async def test_transcribes_and_routes_to_ai(self, mock_ai_backend):
        """Handler transcribes voice and routes text through AI backend."""
        mock_ai_backend.return_value = "Ответ AI"
        update, context = _make_voice_update_and_context()

        # Mock processing message
        processing_msg = MagicMock()
        processing_msg.edit_text = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=processing_msg)

        # Mock Groq client
        mock_transcription = MagicMock()
        mock_transcription.text = "Рассчитай зарплату"

        mock_client_instance = MagicMock()
        mock_client_instance.audio = MagicMock()
        mock_client_instance.audio.transcriptions = MagicMock()
        mock_client_instance.audio.transcriptions.create = AsyncMock(
            return_value=mock_transcription
        )

        with patch(
            "groq.AsyncGroq",
            return_value=mock_client_instance,
        ):
            await voice_message_handler(update, context)

        # Verify AI was called with transcribed text
        mock_ai_backend.assert_called_once_with("Рассчитай зарплату", 12345)
        # Verify response was sent
        processing_msg.edit_text.assert_called_once()
        call_args = processing_msg.edit_text.call_args
        assert "Рассчитай зарплату" in call_args[0][0]
        assert "Ответ AI" in call_args[0][0]

    @pytest.mark.asyncio
    @patch("kindergarten_accountant_bot.handlers.voice_handler.GROQ_API_KEY", "test-key")
    @patch("kindergarten_accountant_bot.handlers.voice_handler._call_ai_backend")
    async def test_empty_transcription(self, mock_ai_backend):
        """Handler handles empty transcription result."""
        update, context = _make_voice_update_and_context()

        processing_msg = MagicMock()
        processing_msg.edit_text = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=processing_msg)

        mock_transcription = MagicMock()
        mock_transcription.text = "   "

        mock_client_instance = MagicMock()
        mock_client_instance.audio = MagicMock()
        mock_client_instance.audio.transcriptions = MagicMock()
        mock_client_instance.audio.transcriptions.create = AsyncMock(
            return_value=mock_transcription
        )

        with patch(
            "groq.AsyncGroq",
            return_value=mock_client_instance,
        ):
            await voice_message_handler(update, context)

        # AI should NOT be called
        mock_ai_backend.assert_not_called()
        processing_msg.edit_text.assert_called_once()
        assert "Не удалось распознать" in processing_msg.edit_text.call_args[0][0]

    @pytest.mark.asyncio
    @patch("kindergarten_accountant_bot.handlers.voice_handler.GROQ_API_KEY", "test-key")
    @patch("kindergarten_accountant_bot.handlers.voice_handler._call_ai_backend")
    async def test_ai_returns_none(self, mock_ai_backend):
        """Handler shows fallback when AI returns None."""
        mock_ai_backend.return_value = None
        update, context = _make_voice_update_and_context()

        processing_msg = MagicMock()
        processing_msg.edit_text = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=processing_msg)

        mock_transcription = MagicMock()
        mock_transcription.text = "Что-то сказал"

        mock_client_instance = MagicMock()
        mock_client_instance.audio = MagicMock()
        mock_client_instance.audio.transcriptions = MagicMock()
        mock_client_instance.audio.transcriptions.create = AsyncMock(
            return_value=mock_transcription
        )

        with patch(
            "groq.AsyncGroq",
            return_value=mock_client_instance,
        ):
            await voice_message_handler(update, context)

        processing_msg.edit_text.assert_called_once()
        call_args = processing_msg.edit_text.call_args
        assert "Что-то сказал" in call_args[0][0]
        assert "не смог обработать" in call_args[0][0]

    @pytest.mark.asyncio
    @patch("kindergarten_accountant_bot.handlers.voice_handler.GROQ_API_KEY", "test-key")
    async def test_handles_exception_gracefully(self):
        """Handler catches exceptions and sends error message."""
        update, context = _make_voice_update_and_context()

        processing_msg = MagicMock()
        processing_msg.edit_text = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=processing_msg)

        # Make get_file raise an exception
        update.message.voice.get_file = AsyncMock(side_effect=Exception("Network error"))

        await voice_message_handler(update, context)

        processing_msg.edit_text.assert_called_once()
        assert "Ошибка" in processing_msg.edit_text.call_args[0][0]
