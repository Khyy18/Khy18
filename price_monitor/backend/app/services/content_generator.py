"""Content generator service - generate video scripts for top deals."""
from __future__ import annotations


import logging

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.models import ContentScript, Product

logger = logging.getLogger(__name__)

class ContentGenerator:
    """Generates video scripts for product reviews and deal announcements."""

    def __init__(self) -> None:
        self._llm: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._llm is None:
            self._llm = AsyncOpenAI(
                api_key=settings.openai_api_key or "not-set",
                base_url=settings.openai_base_url,
            )
        return self._llm

    async def generate_script(
        self, product_id: int, script_type: str, db: AsyncSession
    ) -> dict | None:
        """Generate a video script for a product."""
        result = await db.execute(
            select(Product)
            .options(selectinload(Product.price_history))
            .where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()
        if not product:
            return None

        latest_price = 0.0
        if product.price_history:
            latest = sorted(product.price_history, key=lambda p: p.timestamp, reverse=True)[0]
            latest_price = latest.price

        prompt = self._build_prompt(product, latest_price, script_type)

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Ты копирайтер для коротких видео о товарах. Пиши на русском.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1000,
                temperature=0.8,
            )
            content = response.choices[0].message.content or ""
        except Exception as e:
            logger.error("Content generation failed: %s", e)
            content = f"[Ошибка генерации: {e}]"

        # Save to DB
        script = ContentScript(
            product_id=product_id,
            script_type=script_type,
            content=content,
        )
        db.add(script)
        await db.commit()
        await db.refresh(script)

        return {
            "id": script.id,
            "script_type": script_type,
            "content": content,
            "product_name": product.name,
        }

    def _build_prompt(self, product: Product, price: float, script_type: str) -> str:
        """Build LLM prompt for script generation."""
        price_str = f"{price:,.0f}".replace(",", " ")
        base = f"Товар: {product.name}\nЦена: {price_str} руб.\nМаркетплейс: {product.marketplace}"

        if script_type == "review":
            return f"{base}\n\nНапиши сценарий для 60-секундного видеообзора этого товара."
        elif script_type == "deal":
            return f"{base}\n\nНапиши сценарий для 30-секундного видео о выгодной скидке на этот товар."
        else:
            return f"{base}\n\nНапиши короткий рекламный текст для этого товара."

content_generator = ContentGenerator()
