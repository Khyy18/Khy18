"""Tests for AI handler - /ai command toggle and message processing."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from kindergarten_accountant_bot.handlers.ai_handler import (
    ai_command,
    ai_message_handler,
)


def _make_update_and_context(text="", ai_mode=False):
    """Create mock Update and Context objects."""
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345

    context = MagicMock()
    context.user_data = {"ai_mode": ai_mode}
    return update, context


class TestAiCommand:
    @pytest.mark.asyncio
    async def test_ai_command_toggles_on(self):
        """Test that /ai enables AI mode when it's off."""
        update, context = _make_update_and_context()
        context.user_data = {"ai_mode": False}

        await ai_command(update, context)

        assert context.user_data["ai_mode"] is True
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "AI-режим включён" in call_args[0][0]
        assert call_args[1]["parse_mode"] == "HTML"

    @pytest.mark.asyncio
    async def test_ai_command_toggles_off(self):
        """Test that /ai disables AI mode when it's on."""
        update, context = _make_update_and_context()
        context.user_data = {"ai_mode": True}

        await ai_command(update, context)

        assert context.user_data["ai_mode"] is False
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "AI-режим выключен" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_ai_command_default_state_enables(self):
        """Test that /ai enables AI mode when user_data has no ai_mode key."""
        update, context = _make_update_and_context()
        context.user_data = {}

        await ai_command(update, context)

        assert context.user_data["ai_mode"] is True

    @pytest.mark.asyncio
    async def test_ai_command_response_is_card_format(self):
        """Test that response uses _card() HTML formatting."""
        update, context = _make_update_and_context()
        context.user_data = {"ai_mode": False}

        await ai_command(update, context)

        call_args = update.message.reply_text.call_args
        response_text = call_args[0][0]
        assert "<pre>" in response_text
        assert "</pre>" in response_text
        assert "\u2501" in response_text  # separator char


class TestAiMessageHandler:
    @pytest.mark.asyncio
    async def test_ignores_when_ai_mode_off(self):
        """Test that handler does nothing when AI mode is off."""
        update, context = _make_update_and_context(text="Рассчитай зарплату")
        context.user_data = {"ai_mode": False}

        await ai_message_handler(update, context)

        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_empty_message(self):
        """Test that handler does nothing for empty text."""
        update, context = _make_update_and_context(text="", ai_mode=True)
        update.message.text = ""

        await ai_message_handler(update, context)

        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_none_message(self):
        """Test that handler does nothing for None text."""
        update, context = _make_update_and_context(text=None, ai_mode=True)
        update.message.text = None

        await ai_message_handler(update, context)

        update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    @patch("kindergarten_accountant_bot.handlers.ai_handler._call_ai_backend")
    async def test_processes_text_with_calculation_response(self, mock_backend):
        """Test that calculation-like responses are formatted as cards."""
        mock_backend.return_value = "Расчёт зарплаты:\nНачислено: 30000 руб.\nНа руки: 26100 руб."
        update, context = _make_update_and_context(
            text="Рассчитай зарплату с окладом 30000", ai_mode=True
        )

        await ai_message_handler(update, context)

        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        response_text = call_args[0][0]
        assert "<pre>" in response_text
        assert "Расчёт зарплаты" in response_text
        assert call_args[1]["parse_mode"] == "HTML"

    @pytest.mark.asyncio
    @patch("kindergarten_accountant_bot.handlers.ai_handler._call_ai_backend")
    async def test_processes_text_with_plain_response(self, mock_backend):
        """Test that non-calculation responses are sent as plain text with emoji."""
        mock_backend.return_value = "Срок сдачи 6-НДФЛ - до 25 числа."
        update, context = _make_update_and_context(
            text="Какой срок сдачи 6-НДФЛ?", ai_mode=True
        )

        await ai_message_handler(update, context)

        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        response_text = call_args[0][0]
        assert "\U0001f916" in response_text
        assert "Срок сдачи 6-НДФЛ" in response_text

    @pytest.mark.asyncio
    @patch("kindergarten_accountant_bot.handlers.ai_handler._call_ai_backend")
    async def test_fallback_when_backend_returns_none(self, mock_backend):
        """Test fallback message when AI backend fails."""
        mock_backend.return_value = None
        update, context = _make_update_and_context(
            text="Что-то непонятное", ai_mode=True
        )

        await ai_message_handler(update, context)

        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        response_text = call_args[0][0]
        assert "не удалось обработать" in response_text

    @pytest.mark.asyncio
    @patch("kindergarten_accountant_bot.handlers.ai_handler._call_ai_backend")
    async def test_kbk_response_formatted_as_card(self, mock_backend):
        """Test that KBK search results are formatted as cards."""
        mock_backend.return_value = "Найденные КБК:\n18210102010011000110 - НДФЛ"
        update, context = _make_update_and_context(
            text="Найди КБК для НДФЛ", ai_mode=True
        )

        await ai_message_handler(update, context)

        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        response_text = call_args[0][0]
        assert "<pre>" in response_text
        assert "Найденные КБК" in response_text
