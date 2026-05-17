"""Intelligent LLM router that selects appropriate models based on task type."""
from __future__ import annotations

import enum
import logging
from typing import Any

import redis.asyncio as aioredis

from core.llm import LLMClient

logger = logging.getLogger(__name__)


class TaskType(str, enum.Enum):
    """Types of tasks that map to different LLM models."""

    FAST = "fast"  # Lead scoring, classification
    COMPLEX = "complex"  # Copywriting, conversation
    VOICE = "voice"  # Low latency for voice
    SCORING = "scoring"  # ML scoring tasks


# Default fallback chains: if primary fails, try next
_FALLBACK_CHAINS: dict[TaskType, list[TaskType]] = {
    TaskType.FAST: [TaskType.VOICE],
    TaskType.COMPLEX: [TaskType.FAST],
    TaskType.VOICE: [TaskType.FAST],
    TaskType.SCORING: [TaskType.FAST],
}


class LLMRouter:
    """Routes LLM requests to appropriate models based on task type.

    Provides cost tracking per tenant per model and automatic fallback
    when a primary model fails.
    """

    def __init__(self, settings: Any, redis_url: str) -> None:
        self._settings = settings
        self._redis: aioredis.Redis = aioredis.from_url(redis_url)

        # Model mapping from settings
        self._model_config: dict[TaskType, dict[str, str]] = {
            TaskType.FAST: {
                "provider": "groq",
                "model": getattr(settings, "llm_router_fast_model", "llama3-8b-8192"),
                "api_key": getattr(settings, "groq_api_key", ""),
            },
            TaskType.COMPLEX: {
                "provider": self._detect_complex_provider(settings),
                "model": getattr(settings, "llm_router_complex_model", "claude-3-sonnet-20240229"),
                "api_key": self._get_complex_api_key(settings),
            },
            TaskType.VOICE: {
                "provider": "openai",
                "model": getattr(settings, "llm_router_voice_model", "gpt-4o-mini"),
                "api_key": getattr(settings, "openai_api_key", ""),
            },
            TaskType.SCORING: {
                "provider": "groq",
                "model": getattr(settings, "llm_router_fast_model", "llama3-8b-8192"),
                "api_key": getattr(settings, "groq_api_key", ""),
            },
        }

        # Create LLMClient instances per task type
        self._clients: dict[TaskType, LLMClient] = {}
        for task_type, config in self._model_config.items():
            if config["api_key"]:
                self._clients[task_type] = LLMClient(
                    provider=config["provider"],
                    api_key=config["api_key"],
                    model=config["model"],
                )

    @staticmethod
    def _detect_complex_provider(settings: Any) -> str:
        """Detect which provider to use for complex tasks based on model name."""
        model = getattr(settings, "llm_router_complex_model", "claude-3-sonnet-20240229")
        if "claude" in model:
            return "anthropic"
        return "openai"

    @staticmethod
    def _get_complex_api_key(settings: Any) -> str:
        """Get the API key for the complex model provider."""
        model = getattr(settings, "llm_router_complex_model", "claude-3-sonnet-20240229")
        if "claude" in model:
            return getattr(settings, "anthropic_api_key", "")
        return getattr(settings, "openai_api_key", "")

    async def route_request(
        self,
        task_type: TaskType,
        messages: list[dict[str, Any]],
        tenant_id: str,
        max_tokens: int = 1024,
    ) -> str:
        """Route a request to the appropriate model based on task type.

        Selects the model, generates a response, and tracks cost.
        Falls back to alternative models on failure.

        Args:
            task_type: The type of task to route.
            messages: Chat messages for the LLM.
            tenant_id: Tenant identifier for cost tracking.
            max_tokens: Maximum tokens to generate.

        Returns:
            Generated text response.

        Raises:
            RuntimeError: If all models (primary + fallbacks) fail.
        """
        # Try primary model
        client = self._clients.get(task_type)
        if client is not None:
            try:
                result = await client.generate(messages, max_tokens=max_tokens)
                # Track cost
                # Token estimation: len(utf-8 bytes) // 4 is a rough approximation.
                # This undercounts for non-Latin scripts (Cyrillic, CJK) where tokens
                # are fewer per byte, and overcounts for short English text. For accurate
                # billing, use tiktoken or the provider's usage response field.
                input_text = " ".join(m.get("content", "") for m in messages)
                input_tokens = max(1, len(input_text.encode("utf-8")) // 4)
                output_tokens = max(1, len(result.encode("utf-8")) // 4)
                model_name = self._model_config[task_type]["model"]
                await self.track_cost(tenant_id, model_name, input_tokens, output_tokens)
                return result
            except Exception as exc:
                logger.warning(
                    "Primary model for %s failed: %s. Trying fallback.",
                    task_type.value,
                    str(exc),
                )

        # Try fallback chain
        fallback_types = _FALLBACK_CHAINS.get(task_type, [])
        last_error: Exception | None = None
        for fallback_type in fallback_types:
            fallback_client = self._clients.get(fallback_type)
            if fallback_client is None:
                continue
            try:
                result = await fallback_client.generate(messages, max_tokens=max_tokens)
                input_text = " ".join(m.get("content", "") for m in messages)
                input_tokens = max(1, len(input_text.encode("utf-8")) // 4)
                output_tokens = max(1, len(result.encode("utf-8")) // 4)
                model_name = self._model_config[fallback_type]["model"]
                await self.track_cost(tenant_id, model_name, input_tokens, output_tokens)
                return result
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Fallback model %s also failed: %s",
                    fallback_type.value,
                    str(exc),
                )

        raise RuntimeError(
            f"All models failed for task type {task_type.value}. "
            f"Last error: {last_error}"
        )

    async def track_cost(
        self, tenant_id: str, model: str, input_tokens: int, output_tokens: int
    ) -> None:
        """Record cost in Redis as a per-tenant per-model accumulator.

        Stores as a Redis hash: cost:{tenant_id} with fields for each model.
        """
        hash_key = f"cost:{tenant_id}"
        field_input = f"{model}:input_tokens"
        field_output = f"{model}:output_tokens"
        field_requests = f"{model}:requests"

        try:
            await self._redis.hincrby(hash_key, field_input, input_tokens)
            await self._redis.hincrby(hash_key, field_output, output_tokens)
            await self._redis.hincrby(hash_key, field_requests, 1)
        except Exception as exc:
            logger.warning("Failed to track cost in Redis: %s", exc)

    async def get_cost_summary(self, tenant_id: str) -> dict[str, Any]:
        """Return per-model costs for the current period.

        Returns:
            Dict with model names as keys and their usage stats as values.
        """
        hash_key = f"cost:{tenant_id}"
        try:
            raw_data = await self._redis.hgetall(hash_key)
        except Exception:
            return {}

        # Parse the flat hash into structured per-model data
        models: dict[str, dict[str, int]] = {}
        for field, value in raw_data.items():
            field_str = field.decode() if isinstance(field, bytes) else str(field)
            value_int = int(value.decode() if isinstance(value, bytes) else value)
            parts = field_str.rsplit(":", 1)
            if len(parts) == 2:
                model_name, metric = parts
                if model_name not in models:
                    models[model_name] = {}
                models[model_name][metric] = value_int

        return models

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()
