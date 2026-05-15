"""Tests for international_payments module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import international_payments


@pytest.mark.asyncio
class TestInternationalPayments:
    """Tests for Stripe + Crypto payment system."""

    async def test_create_stripe_session_no_key(self, mock_config, monkeypatch):
        """create_stripe_session returns None when no API key."""
        monkeypatch.setattr(mock_config, "STRIPE_SECRET_KEY", "")
        international_payments._stripe = None  # Reset cached module
        result = await international_payments.create_stripe_session(123, 10.0, "Test")
        assert result is None

    async def test_create_crypto_payment_no_key(self, mock_config, monkeypatch):
        """create_crypto_payment returns None when no API key."""
        monkeypatch.setattr(mock_config, "NOWPAYMENTS_API_KEY", "")
        result = await international_payments.create_crypto_payment(123, 10.0)
        assert result is None

    async def test_get_payment_methods_keyboard(self, mock_config, monkeypatch):
        """get_payment_methods_keyboard returns keyboard with options."""
        monkeypatch.setattr(mock_config, "STRIPE_SECRET_KEY", "")
        monkeypatch.setattr(mock_config, "NOWPAYMENTS_API_KEY", "")
        keyboard = international_payments.get_payment_methods_keyboard(1000.0)
        assert keyboard is not None
        buttons = keyboard.inline_keyboard
        # At least YooKassa + Stars
        assert len(buttons) >= 2

    async def test_get_payment_methods_keyboard_all(self, mock_config, monkeypatch):
        """get_payment_methods_keyboard shows all options when configured."""
        monkeypatch.setattr(mock_config, "STRIPE_SECRET_KEY", "sk_test_123")
        monkeypatch.setattr(mock_config, "NOWPAYMENTS_API_KEY", "api_key_123")
        keyboard = international_payments.get_payment_methods_keyboard(1000.0)
        buttons = keyboard.inline_keyboard
        # YooKassa + Stripe + Crypto + Stars
        assert len(buttons) == 4

    async def test_handle_stripe_webhook_no_secret(self, mock_config, monkeypatch):
        """handle_stripe_webhook returns None when no webhook secret."""
        monkeypatch.setattr(mock_config, "STRIPE_WEBHOOK_SECRET", "")
        result = await international_payments.handle_stripe_webhook(b"payload", "sig")
        assert result is None

    async def test_handle_crypto_webhook_no_secret(self, mock_config, monkeypatch):
        """handle_crypto_webhook returns None when no IPN secret."""
        monkeypatch.setattr(mock_config, "NOWPAYMENTS_IPN_SECRET", "")
        result = await international_payments.handle_crypto_webhook({"status": "finished"})
        assert result is None
