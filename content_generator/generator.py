"""ContentGenerator: AI-генерация контента (кейсы, посты, SEO-тексты).

Все методы используют ai_router.call_llm_text() для генерации.
"""

from __future__ import annotations

import aiohttp

import ai_router
from logging_config import get_logger

log = get_logger(__name__)


class ContentGenerator:
    """Генератор контента через LLM."""

    async def generate_case_study(
        self, session: aiohttp.ClientSession, completed_order: dict
    ) -> str:
        """Сгенерировать кейс на основе выполненного заказа.

        Args:
            session: aiohttp сессия.
            completed_order: словарь с полями title, description, result.

        Returns:
            Текст кейса или пустая строка при ошибке.
        """
        title = (completed_order.get("title", "") or "")[:200]
        description = (completed_order.get("description", "") or "")[:1000]
        result = (completed_order.get("result", "") or "")[:1000]

        prompt = (
            "Write a professional case study in Russian based on this completed project.\n"
            f"Project title: {title}\n"
            f"Description: {description}\n"
            f"Result: {result}\n\n"
            "Structure: Problem, Solution, Result, Technologies used. "
            "Keep it concise (200-300 words)."
        )

        text = await ai_router.call_llm_text(
            session, prompt, max_output_tokens=1024, temperature=0.5
        )
        if text:
            log.info("case_study_generated", title=title)
        return text

    async def generate_channel_post(
        self, session: aiohttp.ClientSession, topic: str
    ) -> str:
        """Сгенерировать пост для Telegram-канала.

        Args:
            session: aiohttp сессия.
            topic: тема поста.

        Returns:
            Текст поста или пустая строка при ошибке.
        """
        prompt = (
            "Write an engaging Telegram channel post in Russian about this topic:\n"
            f"Topic: {topic[:200]}\n\n"
            "Requirements:\n"
            "- Catchy opening\n"
            "- Useful information or insight\n"
            "- Call to action at the end\n"
            "- Use emojis sparingly\n"
            "- 100-200 words max"
        )

        text = await ai_router.call_llm_text(
            session, prompt, max_output_tokens=512, temperature=0.7
        )
        if text:
            log.info("channel_post_generated", topic=topic)
        return text

    async def generate_seo_text(
        self, session: aiohttp.ClientSession, keywords: list[str], length: int = 300
    ) -> str:
        """Сгенерировать SEO-текст по ключевым словам.

        Args:
            session: aiohttp сессия.
            keywords: список ключевых слов.
            length: желаемая длина текста в словах.

        Returns:
            SEO-текст или пустая строка при ошибке.
        """
        kw_str = ", ".join(k[:100] for k in keywords[:20])
        prompt = (
            f"Write an SEO-optimized text in Russian using these keywords: {kw_str}\n\n"
            f"Requirements:\n"
            f"- Approximately {length} words\n"
            f"- Natural keyword integration\n"
            f"- Informative and useful content\n"
            f"- Professional tone"
        )

        text = await ai_router.call_llm_text(
            session, prompt, max_output_tokens=1024, temperature=0.4
        )
        if text:
            log.info("seo_text_generated", keywords=kw_str)
        return text
