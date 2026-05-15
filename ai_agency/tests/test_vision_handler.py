"""Tests for vision_handler module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import vision_handler


@pytest.mark.asyncio
class TestVisionHandler:
    """Tests for image text extraction."""

    async def test_extract_text_from_image_success(self):
        """extract_text_from_image returns extracted text on success."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Extracted text from image"

        with patch.object(vision_handler, "_openai_client", None):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            with patch("vision_handler._get_openai_client", return_value=mock_client):
                result = await vision_handler.extract_text_from_image(b"fake_image")
                assert result == "Extracted text from image"

    async def test_extract_text_from_image_failure(self):
        """extract_text_from_image returns None on API error."""
        with patch.object(vision_handler, "_openai_client", None):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=Exception("API error")
            )
            with patch("vision_handler._get_openai_client", return_value=mock_client):
                result = await vision_handler.extract_text_from_image(b"fake_image")
                assert result is None

    async def test_handle_photo_no_photo(self):
        """handle_photo handles missing photo gracefully."""
        update = MagicMock()
        update.message.photo = []
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        result = await vision_handler.handle_photo(update, context)
        assert result == vision_handler.ENTER_TEXT

    async def test_handle_photo_success(self):
        """handle_photo extracts text and returns ENTER_TEXT."""
        mock_photo = MagicMock()
        mock_photo.file_id = "test_file_id"

        update = MagicMock()
        update.message.photo = [mock_photo]
        update.message.reply_text = AsyncMock()

        mock_file = MagicMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"image"))

        context = MagicMock()
        context.bot.get_file = AsyncMock(return_value=mock_file)
        context.user_data = {}

        with patch(
            "vision_handler.extract_text_from_image",
            new_callable=lambda: lambda: AsyncMock(return_value="OCR text"),
        ):
            with patch("vision_handler.extract_text_from_image", AsyncMock(return_value="OCR text")):
                result = await vision_handler.handle_photo(update, context)
                assert result == vision_handler.ENTER_TEXT
                assert context.user_data["input_text"] == "OCR text"
