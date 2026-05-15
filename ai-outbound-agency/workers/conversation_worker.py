"""Conversation worker tasks for ARQ queue."""

from __future__ import annotations

import logging
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)


async def handle_reply_task(
    ctx: dict[str, Any],
    message_id: str,
) -> dict[str, Any]:
    """Handle an inbound reply via ConversationAgent."""
    from core.llm import LLMClient
    from core.db import async_session_factory
    from integrations.calendar import CalendarIntegration
    from agents.conversation import ConversationAgent

    llm_client = LLMClient(
        provider="openai",
        api_key=settings.openai_api_key,
        model="gpt-4",
    )
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

    result = await conversation_agent.handle_reply(message_id)
    logger.info("Handle reply task completed for message %s: %s", message_id, result)
    return result
