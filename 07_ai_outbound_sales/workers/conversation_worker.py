"""Conversation worker tasks for ARQ queue."""

from __future__ import annotations

import logging
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)


def _build_fallback_llm_client():
    """Build a FallbackLLMClient from settings, matching main.py's approach."""
    from core.llm import FallbackLLMClient

    provider_configs = {
        "openai": {
            "provider": "openai",
            "api_key": settings.openai_api_key,
            "model": settings.llm_openai_model,
            "timeout": settings.llm_openai_timeout,
        },
        "anthropic": {
            "provider": "anthropic",
            "api_key": settings.anthropic_api_key,
            "model": settings.llm_anthropic_model,
            "timeout": settings.llm_anthropic_timeout,
        },
        "groq": {
            "provider": "groq",
            "api_key": settings.groq_api_key,
            "model": settings.llm_groq_model,
            "timeout": settings.llm_groq_timeout,
        },
    }
    chain_names = [
        p.strip()
        for p in settings.llm_fallback_chain.split(",")
        if p.strip()
    ]
    fallback_providers = [
        provider_configs[name]
        for name in chain_names
        if name in provider_configs
    ]

    return FallbackLLMClient(
        providers=fallback_providers,
        redis_url=settings.redis_url,
    )


async def handle_reply_task(
    ctx: dict[str, Any],
    message_id: str,
) -> dict[str, Any]:
    """Handle an inbound reply via ConversationAgent."""
    from core.db import async_session_factory
    from integrations.calendar import CalendarIntegration
    from agents.conversation import ConversationAgent

    llm_client = _build_fallback_llm_client()
    calendar = CalendarIntegration(
        provider=settings.calendar_provider,
        api_key=settings.calcom_api_key,
        base_url=settings.calcom_base_url,
    )
    conversation_agent = ConversationAgent(
        llm_client=llm_client,
        settings=settings,
        calendar=calendar,
        session_factory=async_session_factory,
        email_sender=None,
    )

    try:
        result = await conversation_agent.handle_reply(message_id)
        logger.info("Handle reply task completed for message %s: %s", message_id, result)
        return result
    finally:
        await llm_client.close()
