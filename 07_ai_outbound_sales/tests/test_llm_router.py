"""Tests for the LLM Router module."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.llm_router import LLMRouter, TaskType


@pytest.fixture
def mock_settings():
    """Mock settings for LLM Router."""
    s = MagicMock()
    s.llm_router_fast_model = "llama3-8b-8192"
    s.llm_router_complex_model = "claude-3-sonnet-20240229"
    s.llm_router_voice_model = "gpt-4o-mini"
    s.groq_api_key = "test-groq-key"
    s.anthropic_api_key = "test-anthropic-key"
    s.openai_api_key = "test-openai-key"
    return s


@pytest.fixture
def mock_redis():
    """Mock Redis for LLM Router."""
    redis = AsyncMock()
    redis.hincrby = AsyncMock(return_value=1)
    redis.hgetall = AsyncMock(return_value={})
    redis.close = AsyncMock()
    return redis


@pytest.fixture
def router(mock_settings, mock_redis):
    """Create an LLMRouter with mocked Redis."""
    with patch("core.llm_router.aioredis") as mock_aioredis:
        mock_aioredis.from_url.return_value = mock_redis
        r = LLMRouter(mock_settings, "redis://localhost:6379/0")
        r._redis = mock_redis
        return r


class TestModelSelection:
    """Test that the router selects appropriate models per task type."""

    def test_fast_task_uses_groq(self, router):
        """FAST tasks should route to Groq/Llama model."""
        assert TaskType.FAST in router._model_config
        assert router._model_config[TaskType.FAST]["provider"] == "groq"
        assert router._model_config[TaskType.FAST]["model"] == "llama3-8b-8192"

    def test_complex_task_uses_anthropic(self, router):
        """COMPLEX tasks should route to Anthropic Claude."""
        assert TaskType.COMPLEX in router._model_config
        assert router._model_config[TaskType.COMPLEX]["provider"] == "anthropic"
        assert router._model_config[TaskType.COMPLEX]["model"] == "claude-3-sonnet-20240229"

    def test_voice_task_uses_openai(self, router):
        """VOICE tasks should route to OpenAI GPT-4o-mini."""
        assert TaskType.VOICE in router._model_config
        assert router._model_config[TaskType.VOICE]["provider"] == "openai"
        assert router._model_config[TaskType.VOICE]["model"] == "gpt-4o-mini"

    def test_scoring_task_uses_groq(self, router):
        """SCORING tasks should route to Groq/Llama (same as FAST)."""
        assert TaskType.SCORING in router._model_config
        assert router._model_config[TaskType.SCORING]["provider"] == "groq"


class TestRouteRequest:
    """Test the route_request method."""

    async def test_successful_routing(self, router, mock_redis):
        """Successful routing should return response and track cost."""
        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value="Generated response")
        router._clients[TaskType.FAST] = mock_client

        result = await router.route_request(
            TaskType.FAST,
            [{"role": "user", "content": "Score this lead"}],
            tenant_id="tenant-123",
        )

        assert result == "Generated response"
        mock_client.generate.assert_called_once()
        # Cost should be tracked
        assert mock_redis.hincrby.call_count == 3  # input, output, requests

    async def test_fallback_on_failure(self, router, mock_redis):
        """If primary fails, should try fallback model."""
        # Primary FAST fails
        mock_fast_client = AsyncMock()
        mock_fast_client.generate = AsyncMock(side_effect=RuntimeError("Model down"))
        router._clients[TaskType.FAST] = mock_fast_client

        # Fallback VOICE succeeds
        mock_voice_client = AsyncMock()
        mock_voice_client.generate = AsyncMock(return_value="Fallback response")
        router._clients[TaskType.VOICE] = mock_voice_client

        result = await router.route_request(
            TaskType.FAST,
            [{"role": "user", "content": "Hello"}],
            tenant_id="tenant-123",
        )

        assert result == "Fallback response"
        mock_fast_client.generate.assert_called_once()
        mock_voice_client.generate.assert_called_once()

    async def test_all_models_fail_raises(self, router):
        """If all models fail, should raise RuntimeError."""
        mock_fast_client = AsyncMock()
        mock_fast_client.generate = AsyncMock(side_effect=RuntimeError("Down"))
        router._clients[TaskType.FAST] = mock_fast_client

        mock_voice_client = AsyncMock()
        mock_voice_client.generate = AsyncMock(side_effect=RuntimeError("Also down"))
        router._clients[TaskType.VOICE] = mock_voice_client

        with pytest.raises(RuntimeError, match="All models failed"):
            await router.route_request(
                TaskType.FAST,
                [{"role": "user", "content": "Hello"}],
                tenant_id="tenant-123",
            )


class TestCostTracking:
    """Test cost tracking functionality."""

    async def test_track_cost_records_to_redis(self, router, mock_redis):
        """Cost tracking should write to Redis hash."""
        await router.track_cost("tenant-123", "gpt-4o-mini", 100, 50)

        assert mock_redis.hincrby.call_count == 3
        mock_redis.hincrby.assert_any_call(
            "cost:tenant-123", "gpt-4o-mini:input_tokens", 100
        )
        mock_redis.hincrby.assert_any_call(
            "cost:tenant-123", "gpt-4o-mini:output_tokens", 50
        )
        mock_redis.hincrby.assert_any_call(
            "cost:tenant-123", "gpt-4o-mini:requests", 1
        )

    async def test_get_cost_summary(self, router, mock_redis):
        """Cost summary should parse Redis hash into structured data."""
        mock_redis.hgetall = AsyncMock(return_value={
            b"gpt-4o-mini:input_tokens": b"1000",
            b"gpt-4o-mini:output_tokens": b"500",
            b"gpt-4o-mini:requests": b"10",
            b"llama3-8b-8192:input_tokens": b"2000",
            b"llama3-8b-8192:output_tokens": b"800",
            b"llama3-8b-8192:requests": b"20",
        })

        summary = await router.get_cost_summary("tenant-123")

        assert "gpt-4o-mini" in summary
        assert summary["gpt-4o-mini"]["input_tokens"] == 1000
        assert summary["gpt-4o-mini"]["output_tokens"] == 500
        assert summary["gpt-4o-mini"]["requests"] == 10
        assert "llama3-8b-8192" in summary
        assert summary["llama3-8b-8192"]["requests"] == 20

    async def test_cost_tracking_redis_failure_graceful(self, router, mock_redis):
        """Cost tracking should not raise on Redis failure."""
        mock_redis.hincrby = AsyncMock(side_effect=Exception("Redis down"))

        # Should not raise
        await router.track_cost("tenant-123", "gpt-4o-mini", 100, 50)
