"""Tests for upsell_agent module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import upsell_agent
import database


@pytest.mark.asyncio
class TestUpsellAgent:
    """Tests for post-order upsell system."""

    async def test_addons_defined(self):
        """ADDONS dict has entries for core services."""
        assert "copywriting" in upsell_agent.ADDONS
        assert "rewrite" in upsell_agent.ADDONS
        assert "seo" in upsell_agent.ADDONS
        for service_type, addons in upsell_agent.ADDONS.items():
            assert len(addons) >= 1
            for addon in addons:
                assert "name" in addon
                assert "description" in addon
                assert "price" in addon
                assert addon["price"] > 0

    async def test_get_upsell_keyboard(self):
        """get_upsell_keyboard returns InlineKeyboardMarkup."""
        keyboard = upsell_agent.get_upsell_keyboard(1, "copywriting")
        assert keyboard is not None
        # Should have addons + skip button
        buttons = keyboard.inline_keyboard
        assert len(buttons) >= 2  # at least 1 addon + skip

    async def test_get_upsell_keyboard_unknown_service(self):
        """get_upsell_keyboard returns None for unknown service."""
        keyboard = upsell_agent.get_upsell_keyboard(1, "unknown_service")
        assert keyboard is None

    async def test_generate_upsell_success(self):
        """generate_upsell returns suggestion text."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Try SEO optimization!"

        with patch.object(upsell_agent, "_openai_client", None):
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            with patch("upsell_agent._get_openai_client", return_value=mock_client):
                result = await upsell_agent.generate_upsell("copywriting", "Some result text")
                assert result == "Try SEO optimization!"

    async def test_handle_upsell_purchase_skip(self):
        """handle_upsell_purchase handles skip correctly."""
        update = MagicMock()
        update.callback_query.data = "upsell_skip"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()

        context = MagicMock()
        await upsell_agent.handle_upsell_purchase(update, context)
        update.callback_query.edit_message_text.assert_called_once()

    async def test_handle_upsell_purchase_insufficient_balance(self, initialized_db):
        """handle_upsell_purchase handles insufficient balance."""
        await database.get_or_create_client(telegram_id=500, username="pooruser")
        order_id = await database.create_order(
            client_id=500, service_type="copywriting", input_text="test", price=100.0
        )

        update = MagicMock()
        update.callback_query.data = f"upsell:{order_id}:0"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.effective_user.id = 500

        context = MagicMock()
        await upsell_agent.handle_upsell_purchase(update, context)
        # Should show insufficient funds message
        update.callback_query.edit_message_text.assert_called_once()
