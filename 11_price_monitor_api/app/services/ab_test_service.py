"""A/B testing service for post variants using LLM generation."""

import logging
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Post

logger = logging.getLogger(__name__)

_VARIANT_SYSTEM_PROMPT = """\
Ты копирайтер для Telegram-канала о скидках на маркетплейсах.
Сгенерируй 3 варианта поста о товаре в разных стилях:
- Вариант A: Срочный (создай ощущение дефицита и срочности)
- Вариант B: Информативный (факты, характеристики, сравнение цен)
- Вариант C: Эмоциональный (восторг, личная рекомендация, storytelling)

Формат ответа - строго JSON:
{"A": "текст варианта A", "B": "текст варианта B", "C": "текст варианта C"}

Каждый вариант - HTML для Telegram (теги: <b>, <i>, <s>, <a>).
Длина каждого: 3-5 предложений.
Используй эмодзи.
"""


class ABTestService:
    """A/B testing service for post generation and winner selection."""

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

    async def generate_variants(self, product: dict[str, Any]) -> dict[str, str]:
        """Generate 3 post variants (A/B/C) for a product via LLM.

        Args:
            product: dict with keys name, price, old_price, discount_percent, brand.

        Returns:
            Dict with keys 'A', 'B', 'C' containing post text variants.
        """
        user_message = (
            f"Товар: {product.get('name', 'Товар')}\n"
            f"Бренд: {product.get('brand', 'Нет')}\n"
            f"Цена: {product.get('price', 0):.0f} руб.\n"
            f"Старая цена: {product.get('old_price', 0):.0f} руб.\n"
            f"Скидка: {product.get('discount_percent', 0)}%\n"
        )

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _VARIANT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=1500,
                temperature=0.9,
            )

            import json

            content = response.choices[0].message.content or "{}"
            # Try to parse JSON from the response
            variants = json.loads(content)
            if all(k in variants for k in ("A", "B", "C")):
                return variants
        except Exception as e:
            logger.error("Failed to generate variants: %s", e)

        # Fallback: generate simple variants
        name = product.get("name", "Товар")
        price = product.get("price", 0)
        old_price = product.get("old_price", 0)
        return {
            "A": f"\u26a1 СРОЧНО! <b>{name}</b> всего за {price:.0f} руб (было <s>{old_price:.0f}</s>)! Разбирают!",
            "B": f"\U0001f4ca <b>{name}</b>: цена снижена с {old_price:.0f} до {price:.0f} руб. Выгода {old_price - price:.0f} руб.",
            "C": f"\u2764\ufe0f Нашла отличный <b>{name}</b>! Всего {price:.0f} руб вместо {old_price:.0f}! Рекомендую!",
        }

    async def select_winner(self, post_id: int, db: AsyncSession) -> str | None:
        """Select the winning variant based on highest CTR.

        Checks all variants for the same product and returns the variant
        letter (A/B/C) with the highest click-through rate.
        """
        # Find the post and its product
        result = await db.execute(select(Post).where(Post.id == post_id))
        post = result.scalar_one_or_none()
        if not post:
            return None

        # Get all variants for this product
        result = await db.execute(
            select(Post).where(
                Post.product_id == post.product_id,
                Post.variant.isnot(None),
            )
        )
        variants = list(result.scalars().all())

        if not variants:
            return None

        # Find variant with highest CTR
        best_variant = None
        best_ctr = -1.0

        for v in variants:
            ctr = v.ctr if v.ctr else 0.0
            if v.impressions and v.impressions > 0:
                ctr = v.clicks / v.impressions
            if ctr > best_ctr:
                best_ctr = ctr
                best_variant = v.variant

        return best_variant
