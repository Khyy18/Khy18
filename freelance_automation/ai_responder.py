"""AI-генерация уникальных откликов на фриланс-заказы.

Использует ai_router для генерации персонализированных ответов,
адаптированных под конкретную платформу и заказ.
"""

from __future__ import annotations

from typing import Optional

import aiohttp

import ai_router
from freelance_automation.base import Order
from logging_config import get_logger

log = get_logger(__name__)

# Шаблон-заглушка на случай сбоя LLM
_FALLBACK_TEMPLATE = (
    "Здравствуйте! Заинтересовал ваш проект \"{title}\". "
    "Имею релевантный опыт и готов обсудить детали. "
    "Буду рад сотрудничеству!"
)


class AIResponder:
    """Генератор AI-откликов на фриланс-заказы."""

    async def generate_response(
        self,
        session: aiohttp.ClientSession,
        order: Order,
        platform: str,
        portfolio_items: Optional[list[str]] = None,
    ) -> str:
        """Сгенерировать уникальный отклик через LLM.

        Args:
            session: aiohttp сессия для HTTP запросов.
            order: Заказ, на который генерируем отклик.
            platform: Название платформы (kwork, fl.ru).
            portfolio_items: Список релевантных работ из портфолио.

        Returns:
            Сгенерированный текст отклика или fallback-шаблон.
        """
        items = portfolio_items or []
        budget_str = str(int(order.budget)) if order.budget else "договорный"

        # Truncate user-controlled inputs to prevent prompt injection / token overflow
        title = (order.title or "")[:200]
        description = (order.description or "")[:1000]

        prompt = (
            f"Analyze this job posting: {title}\n"
            f"{description}\n"
            f"Budget: {budget_str}\n"
            f"Platform: {platform}\n"
            f"Relevant portfolio: {items}\n"
            f"Generate a unique, professional response in Russian. "
            f"Adapt tone for {platform} "
            f"(kwork=concise/professional, fl.ru=detailed/friendly). "
            f"Include relevant portfolio mention. Max 500 chars."
        )

        try:
            response = await ai_router.call_llm_text(
                session,
                prompt,
                max_output_tokens=300,
                temperature=0.7,
            )
            if response and response.strip():
                log.info(
                    "ai_response_generated",
                    platform=platform,
                    order_id=order.id,
                )
                return response.strip()
        except Exception as e:
            log.error("ai_response_error", error=str(e))

        # Fallback
        log.warning("ai_response_fallback", order_id=order.id)
        return _FALLBACK_TEMPLATE.format(title=order.title)
