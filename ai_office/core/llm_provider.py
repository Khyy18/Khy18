"""LLM Multi-Provider с retry, fallback и трекингом токенов."""

import asyncio
import logging
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from ai_office.core.config import settings
from ai_office.core.rate_limiter import (
    BudgetExhaustedError,
    Priority,
    RateLimitedError,
    budget_tracker,
    rate_limiter,
)

logger = logging.getLogger(__name__)

# Per-token pricing (USD per token)
TOKEN_PRICING = {
    "gpt-4o-mini": {"prompt": 0.00000015, "completion": 0.0000006},
    "gpt-4o": {"prompt": 0.0000025, "completion": 0.00001},
    "gpt-4": {"prompt": 0.00003, "completion": 0.00006},
    "gpt-3.5-turbo": {"prompt": 0.0000005, "completion": 0.0000015},
    "claude-3-5-sonnet-20241022": {"prompt": 0.000003, "completion": 0.000015},
    "claude-3-haiku-20240307": {"prompt": 0.00000025, "completion": 0.00000125},
    "llama-3.3-70b-versatile": {"prompt": 0.00000059, "completion": 0.00000079},
    "llama-3.1-8b-instant": {"prompt": 0.00000005, "completion": 0.00000008},
    "mixtral-8x7b-32768": {"prompt": 0.00000024, "completion": 0.00000024},
}

# Default pricing for unknown models
DEFAULT_PRICING = {"prompt": 0.000001, "completion": 0.000002}


def _get_anthropic_class():
    """Import ChatAnthropic with graceful fallback."""
    try:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic
    except ImportError:
        return None


def _get_groq_class():
    """Import ChatGroq with graceful fallback."""
    try:
        from langchain_groq import ChatGroq
        return ChatGroq
    except ImportError:
        return None


class LLMProvider:
    """Multi-provider LLM с retry, fallback и cost tracking."""

    def __init__(self):
        self._providers = self._build_provider_list()
        self._current_index = 0

    def _build_provider_list(self) -> list[str]:
        """Построить список провайдеров из настроек."""
        providers_str = settings.llm_providers or "openai"
        return [p.strip() for p in providers_str.split(",") if p.strip()]

    def _create_chat_model(self, provider: str, **kwargs) -> Any:
        """Создать экземпляр ChatModel для провайдера."""
        temperature = kwargs.get("temperature", 0.7)

        if provider == "openai":
            return ChatOpenAI(
                model=settings.openai_model,
                api_key=settings.openai_api_key,
                temperature=temperature,
            )
        elif provider == "anthropic":
            ChatAnthropic = _get_anthropic_class()
            if ChatAnthropic is None:
                raise ImportError("langchain-anthropic not installed")
            return ChatAnthropic(
                model="claude-3-5-sonnet-20241022",
                api_key=settings.anthropic_api_key,
                temperature=temperature,
            )
        elif provider == "groq":
            ChatGroq = _get_groq_class()
            if ChatGroq is None:
                raise ImportError("langchain-groq not installed")
            return ChatGroq(
                model="llama-3.3-70b-versatile",
                api_key=settings.groq_api_key,
                temperature=temperature,
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def get_chat_model(self, **kwargs) -> Any:
        """Получить текущий активный ChatModel."""
        provider = self._providers[self._current_index]
        return self._create_chat_model(provider, **kwargs)

    def _estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Оценить стоимость вызова."""
        pricing = TOKEN_PRICING.get(model, DEFAULT_PRICING)
        return (prompt_tokens * pricing["prompt"]) + (completion_tokens * pricing["completion"])

    def _get_model_name(self, provider: str) -> str:
        """Получить имя модели для провайдера."""
        if provider == "openai":
            return settings.openai_model
        elif provider == "anthropic":
            return "claude-3-5-sonnet-20241022"
        elif provider == "groq":
            return "llama-3.3-70b-versatile"
        return "unknown"

    async def _log_usage(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        agent_name: str,
    ):
        """Записать использование токенов в БД."""
        from ai_office.core.database import async_session
        from ai_office.core.models import TokenUsage

        cost = self._estimate_cost(model, prompt_tokens, completion_tokens)

        # Track spend in budget
        await budget_tracker.add_spend(cost)

        try:
            async with async_session() as session:
                usage = TokenUsage(
                    provider=provider,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    estimated_cost_usd=cost,
                    agent_name=agent_name,
                )
                session.add(usage)
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to log token usage: {e}")

    def _extract_token_usage(self, response) -> tuple[int, int]:
        """Извлечь prompt/completion tokens из ответа LLM."""
        prompt_tokens = 0
        completion_tokens = 0

        if hasattr(response, "response_metadata"):
            metadata = response.response_metadata or {}
            token_usage = metadata.get("token_usage", {})
            if token_usage:
                prompt_tokens = token_usage.get("prompt_tokens", 0)
                completion_tokens = token_usage.get("completion_tokens", 0)
            else:
                # Anthropic-style usage
                usage = metadata.get("usage", {})
                if usage:
                    prompt_tokens = usage.get("input_tokens", 0)
                    completion_tokens = usage.get("output_tokens", 0)

        # Fallback: estimate from content length
        if prompt_tokens == 0 and completion_tokens == 0:
            content = getattr(response, "content", "") or ""
            completion_tokens = max(1, len(content) // 4)
            prompt_tokens = completion_tokens * 3  # rough estimate

        return prompt_tokens, completion_tokens

    async def ainvoke_with_retry(
        self,
        messages: list,
        agent_name: str = "unknown",
        tools: Optional[list] = None,
        priority: Priority = Priority.NORMAL,
        **kwargs,
    ) -> Any:
        """Вызвать LLM с retry и fallback.

        Args:
            messages: Список сообщений для LLM.
            agent_name: Имя агента (для трекинга).
            tools: Список инструментов (опционально).
            priority: Приоритет запроса.

        Returns:
            Ответ LLM (AIMessage).

        Raises:
            BudgetExhaustedError: Если бюджет исчерпан.
            RateLimitedError: Если лимит запросов исчерпан.
            Exception: Если все провайдеры не доступны.
        """
        # Check budget
        if settings.enable_rate_limiter:
            await budget_tracker.check_budget()
            await rate_limiter.acquire(agent_name, priority)

        last_error: Optional[Exception] = None

        for provider_idx, provider in enumerate(self._providers):
            # Try this provider with retries
            for attempt in range(settings.llm_max_retries):
                try:
                    model = self._create_chat_model(provider, **kwargs)
                    if tools:
                        model = model.bind_tools(tools)

                    response = await model.ainvoke(messages)

                    # Log usage
                    model_name = self._get_model_name(provider)
                    prompt_tokens, completion_tokens = self._extract_token_usage(response)
                    await self._log_usage(
                        provider=provider,
                        model=model_name,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        agent_name=agent_name,
                    )

                    # Update current index to successful provider
                    self._current_index = provider_idx
                    return response

                except (BudgetExhaustedError, RateLimitedError):
                    raise
                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"LLM call failed (provider={provider}, attempt={attempt + 1}): {e}"
                    )
                    if attempt < settings.llm_max_retries - 1:
                        backoff = 2**attempt  # 1s, 2s, 4s
                        await asyncio.sleep(backoff)

            # All retries exhausted for this provider, try next
            logger.warning(f"Provider '{provider}' exhausted all retries, trying fallback...")

        # All providers failed
        raise last_error or RuntimeError("All LLM providers failed")


# Module-level singleton instance
llm_provider = LLMProvider()
