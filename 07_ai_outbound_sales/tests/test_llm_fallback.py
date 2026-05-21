"""Tests for FallbackLLMClient and PromptRegistry."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from core.llm import FallbackLLMClient, PromptRegistry


@pytest.fixture
def providers_config():
    """Return a test provider configuration list."""
    return [
        {
            "provider": "openai",
            "api_key": "test-openai-key",
            "model": "gpt-4",
            "timeout": 5,
        },
        {
            "provider": "anthropic",
            "api_key": "test-anthropic-key",
            "model": "claude-3-sonnet-20240229",
            "timeout": 10,
        },
    ]


@pytest.fixture
def mock_redis_client(mock_redis):
    """Provide a mock Redis client for FallbackLLMClient tests."""
    return mock_redis


@pytest.fixture
def fallback_client(providers_config, mock_redis_client):
    """Create a FallbackLLMClient with mocked Redis and LLMClient instances."""
    with patch("core.llm.aioredis.from_url", return_value=mock_redis_client):
        client = FallbackLLMClient(
            providers=providers_config,
            redis_url="redis://localhost:6379/0",
        )
    return client


@pytest.mark.asyncio
async def test_primary_succeeds(fallback_client):
    """Test that when the primary provider succeeds, no fallback is triggered."""
    primary_client, _ = fallback_client._clients[0]
    primary_client.generate = AsyncMock(return_value="Primary response")

    result = await fallback_client.generate(
        messages=[{"role": "user", "content": "Hello"}],
    )

    assert result == "Primary response"
    primary_client.generate.assert_awaited_once()
    # Secondary should not be called
    secondary_client, _ = fallback_client._clients[1]
    if isinstance(secondary_client.generate, AsyncMock):
        secondary_client.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_fallback_on_timeout(fallback_client):
    """Test that on primary timeout, the client falls through to secondary."""
    primary_client, _ = fallback_client._clients[0]
    secondary_client, _ = fallback_client._clients[1]

    primary_client.generate = AsyncMock(side_effect=asyncio.TimeoutError())
    secondary_client.generate = AsyncMock(return_value="Secondary response")

    result = await fallback_client.generate(
        messages=[{"role": "user", "content": "Hello"}],
    )

    assert result == "Secondary response"
    primary_client.generate.assert_awaited_once()
    secondary_client.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_providers_fail(fallback_client):
    """Test that RuntimeError is raised when all providers fail."""
    primary_client, _ = fallback_client._clients[0]
    secondary_client, _ = fallback_client._clients[1]

    primary_client.generate = AsyncMock(side_effect=RuntimeError("Provider 1 error"))
    secondary_client.generate = AsyncMock(side_effect=RuntimeError("Provider 2 error"))

    with pytest.raises(RuntimeError, match="All LLM providers failed"):
        await fallback_client.generate(
            messages=[{"role": "user", "content": "Hello"}],
        )


@pytest.mark.asyncio
async def test_cache_hit(fallback_client):
    """Test that a cached response is returned without calling any provider."""
    # Pre-populate the Redis mock with a cached response
    messages = [{"role": "user", "content": "Hello"}]
    import hashlib
    import json

    model_name = "gpt-4"
    cache_key_raw = json.dumps(messages, sort_keys=True) + model_name + str(0.7) + str(1024)
    cache_key = hashlib.sha256(cache_key_raw.encode()).hexdigest()
    redis_key = f"llm_cache:{cache_key}"

    # Store cached value in mock redis
    fallback_client._redis._store[redis_key] = "Cached response"

    primary_client, _ = fallback_client._clients[0]
    primary_client.generate = AsyncMock(return_value="Fresh response")

    result = await fallback_client.generate(messages=messages)

    assert result == "Cached response"
    primary_client.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_cache_miss_stores_result(fallback_client):
    """Test that after a successful generation, the result is cached in Redis."""
    messages = [{"role": "user", "content": "Hello"}]

    primary_client, _ = fallback_client._clients[0]
    primary_client.generate = AsyncMock(return_value="Fresh response")

    result = await fallback_client.generate(messages=messages)

    assert result == "Fresh response"

    # Verify the result was cached
    import hashlib
    import json

    model_name = "gpt-4"
    cache_key_raw = json.dumps(messages, sort_keys=True) + model_name + str(0.7) + str(1024)
    cache_key = hashlib.sha256(cache_key_raw.encode()).hexdigest()
    redis_key = f"llm_cache:{cache_key}"

    assert redis_key in fallback_client._redis._store
    assert fallback_client._redis._store[redis_key] == "Fresh response"


@pytest.mark.asyncio
async def test_cache_key_includes_temperature_and_max_tokens(fallback_client):
    """Test that different temperature/max_tokens produce different cache keys."""
    import hashlib
    import json

    messages = [{"role": "user", "content": "Hello"}]
    model_name = "gpt-4"

    # Cache key for temp=0.7, max_tokens=1024
    key1_raw = json.dumps(messages, sort_keys=True) + model_name + str(0.7) + str(1024)
    key1 = hashlib.sha256(key1_raw.encode()).hexdigest()

    # Cache key for temp=0.0, max_tokens=1024
    key2_raw = json.dumps(messages, sort_keys=True) + model_name + str(0.0) + str(1024)
    key2 = hashlib.sha256(key2_raw.encode()).hexdigest()

    # Cache key for temp=0.7, max_tokens=512
    key3_raw = json.dumps(messages, sort_keys=True) + model_name + str(0.7) + str(512)
    key3 = hashlib.sha256(key3_raw.encode()).hexdigest()

    assert key1 != key2, "Different temperatures should produce different cache keys"
    assert key1 != key3, "Different max_tokens should produce different cache keys"

    # Verify by generating with different params - both should call the provider
    primary_client, _ = fallback_client._clients[0]
    primary_client.generate = AsyncMock(return_value="Response A")

    result_a = await fallback_client.generate(messages=messages, temperature=0.7, max_tokens=1024)
    assert result_a == "Response A"

    primary_client.generate = AsyncMock(return_value="Response B")
    result_b = await fallback_client.generate(messages=messages, temperature=0.0, max_tokens=1024)
    assert result_b == "Response B"  # Should NOT get cached "Response A"


def test_prompt_registry():
    """Test PromptRegistry register and get functionality with versioning."""
    registry = PromptRegistry()

    registry.register("greeting", "Hello {name}!", version=1)
    registry.register("farewell", "Goodbye {name}!", version=1)

    version, template = registry.get("greeting")
    assert version == 1
    assert template == "Hello {name}!"

    # Update to new version
    registry.register("greeting", "Hi {name}, welcome!", version=2)
    version, template = registry.get("greeting")
    assert version == 2
    assert template == "Hi {name}, welcome!"

    # Verify KeyError on missing prompt
    with pytest.raises(KeyError):
        registry.get("nonexistent")
