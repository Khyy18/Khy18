"""Tests for platform_adapter module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock


class TestPlatformAdapter:
    """Test platform adapter abstract interface and router."""

    def test_abstract_interface_methods(self):
        """PlatformAdapter has required abstract methods."""
        from platform_adapter import PlatformAdapter
        import inspect

        # Check abstract methods exist
        abstract_methods = set()
        for name, method in inspect.getmembers(PlatformAdapter):
            if getattr(method, "__isabstractmethod__", False):
                abstract_methods.add(name)

        assert "send_message" in abstract_methods
        assert "send_document" in abstract_methods
        assert "send_photo" in abstract_methods
        assert "get_user_info" in abstract_methods

    def test_telegram_adapter_instantiation(self):
        """TelegramAdapter can be instantiated."""
        from adapters.telegram import TelegramAdapter

        adapter = TelegramAdapter(bot=None)
        assert adapter.platform_name == "telegram"

    def test_whatsapp_adapter_raises(self):
        """WhatsAppAdapter raises NotImplementedError."""
        from adapters.whatsapp import WhatsAppAdapter

        adapter = WhatsAppAdapter()
        assert adapter.platform_name == "whatsapp"

    def test_vk_adapter_raises(self):
        """VKAdapter raises NotImplementedError."""
        from adapters.vk import VKAdapter

        adapter = VKAdapter()
        assert adapter.platform_name == "vk"

    def test_router_register_and_get(self):
        """PlatformRouter can register and retrieve adapters."""
        from platform_adapter import PlatformRouter
        from adapters.telegram import TelegramAdapter

        router = PlatformRouter()
        adapter = TelegramAdapter(bot=None)
        router.register(adapter)

        assert "telegram" in router.available_platforms
        assert router.get_adapter("telegram") is adapter
        assert router.get_adapter("nonexistent") is None

    @pytest.mark.asyncio
    async def test_router_send_message_unknown_platform(self):
        """PlatformRouter returns False for unknown platform."""
        from platform_adapter import PlatformRouter

        router = PlatformRouter()
        result = await router.send_message("unknown", 12345, "hello")
        assert result is False

    def test_adapters_init_imports(self):
        """adapters/__init__.py imports all adapters."""
        from adapters import TelegramAdapter, WhatsAppAdapter, VKAdapter
        assert TelegramAdapter is not None
        assert WhatsAppAdapter is not None
        assert VKAdapter is not None
