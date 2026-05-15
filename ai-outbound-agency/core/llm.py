import asyncio
import time
from typing import Any

import anthropic
import openai

from core.observability import llm_requests_total, llm_latency_seconds, llm_errors_total


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
