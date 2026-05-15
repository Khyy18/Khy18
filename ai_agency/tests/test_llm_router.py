"""Tests for LLM router module: provider priority, fallback, cheapest selection."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import llm_router
from llm_router import LLMProvider, ProviderMetrics, _select_provider, _call_provider


@pytest.fixture(autouse=True)
def reset_providers():
    """Reset the singleton providers list between tests."""
    llm_router._providers = None
    yield
    llm_router._providers = None


def _make_provider(name, priority, cost, healthy=True):
    """Helper to create a test provider."""
    p = LLMProvider(name=name, priority=priority, cost_per_token=cost)
    p._healthy = healthy
    p._circuit = None  # Disable circuit breaker for tests
    p._client = AsyncMock()
    return p


@pytest.mark.asyncio
class TestLLMRouter:

    async def test_generate_uses_first_healthy_provider(self, monkeypatch):
        """generate() picks the cheapest healthy provider and uses it."""
        provider_a = _make_provider("openai", 0, 0.00003)
        provider_b = _make_provider("groq", 1, 0.000005)

        providers = [provider_a, provider_b]
        monkeypatch.setattr(llm_router, "_providers", providers)

        # groq is cheapest so it should be selected first
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello from groq"
        provider_b._client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("llm_router._call_provider", wraps=llm_router._call_provider):
            result = await llm_router.generate(
                [{"role": "user", "content": "test"}]
            )

        assert result == "Hello from groq"

    async def test_generate_fallback_on_error(self, monkeypatch):
        """If the cheapest provider fails, generate() falls back to next available."""
        provider_a = _make_provider("openai", 0, 0.00003)
        provider_b = _make_provider("groq", 1, 0.000005)

        providers = [provider_a, provider_b]
        monkeypatch.setattr(llm_router, "_providers", providers)

        # groq (cheapest) fails
        provider_b._client.chat.completions.create = AsyncMock(
            side_effect=Exception("Groq error")
        )

        # openai succeeds
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello from openai"
        provider_a._client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await llm_router.generate(
            [{"role": "user", "content": "test"}]
        )

        assert result == "Hello from openai"

    async def test_cheapest_provider_selection(self):
        """_select_provider returns the cheapest available provider."""
        expensive = _make_provider("openai", 0, 0.00003)
        cheap = _make_provider("groq", 1, 0.000005)
        medium = _make_provider("anthropic", 2, 0.000025)

        providers = [expensive, medium, cheap]
        selected = _select_provider(providers)
        assert selected.name == "groq"

    async def test_all_providers_fail_returns_none(self, monkeypatch):
        """When all providers fail, generate() returns None."""
        provider_a = _make_provider("openai", 0, 0.00003)
        provider_b = _make_provider("groq", 1, 0.000005)

        providers = [provider_a, provider_b]
        monkeypatch.setattr(llm_router, "_providers", providers)

        # Both fail
        provider_a._client.chat.completions.create = AsyncMock(
            side_effect=Exception("OpenAI error")
        )
        provider_b._client.chat.completions.create = AsyncMock(
            side_effect=Exception("Groq error")
        )

        result = await llm_router.generate(
            [{"role": "user", "content": "test"}]
        )

        assert result is None

    async def test_unhealthy_provider_skipped(self):
        """_select_provider skips providers marked as unhealthy."""
        healthy = _make_provider("openai", 0, 0.00003, healthy=True)
        unhealthy = _make_provider("groq", 1, 0.000005, healthy=False)

        providers = [healthy, unhealthy]
        selected = _select_provider(providers)
        # groq is cheapest but unhealthy, so openai should be selected
        assert selected.name == "openai"
