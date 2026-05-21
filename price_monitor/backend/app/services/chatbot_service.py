"""AI chatbot service with RAG product search."""
from __future__ import annotations


import logging
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.models import Product

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Ты - умный ассистент для поиска товаров на российских маркетплейсах. "
    "Помогай пользователям найти товары в рамках их бюджета. Отвечай на русском языке. "
    "Форматируй рекомендации товаров в виде структурированных карточек."
)

class ChatbotService:
    """Chatbot service that searches products and answers via LLM."""

    def __init__(self) -> None:
        self._llm: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """Lazy-initialize the OpenAI client."""
        if self._llm is None:
            self._llm = AsyncOpenAI(
                api_key=settings.openai_api_key or "not-set",
                base_url=settings.openai_base_url,
            )
        return self._llm

    async def answer(self, message: str, db: AsyncSession) -> dict[str, Any]:
        """Process user message: search products, build context, call LLM."""
        keywords = self._extract_keywords(message)
        products = await self._search_products(keywords, db)
        context = self._build_context(products)
        reply = await self._call_llm(message, context)
        product_ids = [p.id for p in products]
        return {"reply": reply, "product_ids": product_ids, "products": products}

    def _extract_keywords(self, message: str) -> list[str]:
        """Extract keywords from user message."""
        words = message.lower().split()
        return [w for w in words if len(w) >= 3]

    async def _search_products(self, keywords: list[str], db: AsyncSession) -> list[Product]:
        """Search products by keywords."""
        if not keywords:
            return []

        conditions = []
        for kw in keywords:
            pattern = f"%{kw}%"
            conditions.append(Product.name.ilike(pattern))
            conditions.append(Product.category.ilike(pattern))

        query = (
            select(Product)
            .options(selectinload(Product.price_history))
            .where(or_(*conditions))
            .limit(10)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    def _build_context(self, products: list[Product]) -> str:
        """Build context string from found products."""
        MAX_CONTEXT_CHARS = 2000
        if not products:
            return "Товары не найдены в базе данных."

        lines = ["Найденные товары:"]
        current_length = len(lines[0])

        for p in products:
            latest_price = 0.0
            if p.price_history:
                latest = sorted(p.price_history, key=lambda ph: ph.timestamp, reverse=True)[0]
                latest_price = latest.price
            line = (
                f"- {p.name} ({p.marketplace}): {latest_price:.0f} руб. "
                f"[категория: {p.category or 'нет'}]"
            )
            if current_length + len(line) + 1 > MAX_CONTEXT_CHARS:
                lines.append(f"... (ещё {len(products) - len(lines) + 1} товаров не показано)")
                break
            lines.append(line)
            current_length += len(line) + 1

        return "\n".join(lines)

    async def _call_llm(self, user_message: str, context: str) -> str:
        """Call OpenAI-compatible API with product context."""
        max_user_msg_len = 500
        if len(user_message) > max_user_msg_len:
            user_message = user_message[:max_user_msg_len] + "..."

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Контекст товаров:\n{context}\n\nВопрос пользователя: {user_message}",
                    },
                ],
                max_tokens=800,
                temperature=0.7,
            )
            return response.choices[0].message.content or "Извините, не удалось получить ответ."
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            return "Извините, сервис временно недоступен. Попробуйте позже."

chatbot_service = ChatbotService()
