import asyncio
import hashlib
import json
import logging
import time
from typing import Any

import anthropic
import openai
import redis.asyncio as aioredis

from core.observability import (
    llm_requests_total,
    llm_latency_seconds,
    llm_errors_total,
    fallback_triggered_total,
)

logger = logging.getLogger(__name__)


class LLMClient:
    """Universal async LLM client supporting OpenAI, Anthropic, and Groq."""

    _GROQ_BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self, provider: str, api_key: str, model: str) -> None:
        self.provider = provider.lower()
        self.model = model
        self.api_key = api_key

        if self.provider in ("openai", "groq"):
            base_url = self._GROQ_BASE_URL if self.provider == "groq" else None
            self._openai_client = openai.AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
            )
        elif self.provider == "anthropic":
            self._anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def generate(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Generate a response from the LLM with retry logic."""
        last_error: Exception | None = None

        llm_requests_total.labels(provider=self.provider, model=self.model).inc()

        for attempt in range(3):
            try:
                start_time = time.monotonic()
                if self.provider in ("openai", "groq"):
                    result = await self._generate_openai(
                        messages, temperature, max_tokens
                    )
                elif self.provider == "anthropic":
                    result = await self._generate_anthropic(
                        messages, temperature, max_tokens
                    )
                else:
                    raise ValueError(f"Unsupported provider: {self.provider}")
                elapsed = time.monotonic() - start_time
                llm_latency_seconds.labels(provider=self.provider).observe(elapsed)
                return result
            except Exception as exc:
                last_error = exc
                llm_errors_total.labels(provider=self.provider).inc()
                if attempt < 2:
                    await asyncio.sleep(2**attempt)

        raise RuntimeError(
            f"LLM generation failed after 3 attempts: {last_error}"
        ) from last_error

    async def _generate_openai(
        self,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        response = await self._openai_client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        return content or ""

    async def _generate_anthropic(
        self,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> str:
        # Extract system message if present
        system_message: str | None = None
        user_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.get("role") == "system":
                system_message = msg["content"]
            else:
                user_messages.append(msg)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": user_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_message:
            kwargs["system"] = system_message

        response = await self._anthropic_client.messages.create(**kwargs)
        content_block = response.content[0]
        return content_block.text if hasattr(content_block, "text") else str(content_block)


class FallbackLLMClient:
    """LLM client with fallback chain, response caching, and per-provider timeouts."""

    def __init__(self, providers: list[dict[str, Any]], redis_url: str) -> None:
        """Initialize fallback client with ordered provider list and Redis for caching.

        Args:
            providers: List of dicts with keys: provider, api_key, model, timeout.
            redis_url: Redis connection URL for response caching.
        """
        self.providers = providers
        self._clients: list[tuple[LLMClient, float]] = []
        for p in providers:
            client = LLMClient(
                provider=p["provider"],
                api_key=p["api_key"],
                model=p["model"],
            )
            self._clients.append((client, float(p["timeout"])))
        self._redis: aioredis.Redis = aioredis.from_url(redis_url)

    async def generate(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Generate response trying each provider in order with caching.

        Checks Redis cache first. On cache miss, tries providers sequentially
        with per-provider timeouts. Caches successful responses for 24 hours.

        Raises:
            RuntimeError: If all providers fail.
        """
        # Use first provider's model for cache key
        model_name = self.providers[0]["model"] if self.providers else ""
        cache_key_raw = json.dumps(messages, sort_keys=True) + model_name
        cache_key = hashlib.sha256(cache_key_raw.encode()).hexdigest()
        redis_key = f"llm_cache:{cache_key}"

        # Check cache
        try:
            cached = await self._redis.get(redis_key)
            if cached is not None:
                return cached.decode() if isinstance(cached, bytes) else str(cached)
        except Exception:
            pass

        # Try each provider in order
        last_error: Exception | None = None
        for i, (client, timeout) in enumerate(self._clients):
            try:
                result = await asyncio.wait_for(
                    client.generate(messages, temperature, max_tokens),
                    timeout=timeout,
                )
                # Cache successful response with 24h TTL
                try:
                    await self._redis.setex(redis_key, 86400, result)
                except Exception:
                    pass
                return result
            except (asyncio.TimeoutError, Exception) as exc:
                last_error = exc
                provider_name = self.providers[i]["provider"]
                logger.warning(
                    "Provider %s failed: %s. Trying next provider.",
                    provider_name,
                    str(exc),
                )
                fallback_triggered_total.labels(provider=provider_name).inc()

        raise RuntimeError(
            f"All LLM providers failed. Last error: {last_error}"
        )

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()


class PromptRegistry:
    """Registry for versioned prompt templates."""

    def __init__(self) -> None:
        self._prompts: dict[str, dict[str, Any]] = {}

    def register(self, name: str, template: str, version: int) -> None:
        """Register a prompt template with a version number.

        Args:
            name: Unique name for the prompt.
            template: The prompt template string.
            version: Version number for tracking.
        """
        self._prompts[name] = {"version": version, "template": template}

    def get(self, name: str) -> tuple[int, str]:
        """Retrieve the latest version and template for a prompt.

        Args:
            name: The prompt name to look up.

        Returns:
            Tuple of (version, template).

        Raises:
            KeyError: If prompt name is not registered.
        """
        entry = self._prompts[name]
        return entry["version"], entry["template"]
