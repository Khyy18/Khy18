"""Суммаризация отзывов через LLM."""

import logging

from openai import AsyncOpenAI

from bot.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Ты аналитик отзывов на маркетплейсах. Получаешь список отзывов покупателей.
Твоя задача - написать краткую сводку из 2-3 предложений на русском языке.
Выдели главные плюсы и минусы товара по мнению покупателей.
Пиши сухо и информативно, без маркетинговых преувеличений.
"""


class ReviewsSummarizer:
    """Суммаризация отзывов через OpenAI-совместимый API."""

    def __init__(self) -> None:
        self._llm = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

    async def summarize(self, reviews: list[str]) -> str:
        """Создать краткую сводку отзывов.

        Args:
            reviews: список текстов отзывов.

        Returns:
            Краткая сводка (2-3 предложения) или пустая строка.
        """
        if not reviews:
            return ""

        # Ограничим количество отзывов для промпта
        reviews_text = "\n---\n".join(reviews[:15])

        try:
            response = await self._llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"Отзывы:\n{reviews_text}"},
                ],
                max_tokens=200,
                temperature=0.3,
            )

            summary = response.choices[0].message.content or ""
            return summary.strip()
        except Exception as e:
            logger.error("Ошибка суммаризации отзывов: %s", e)
            return ""
