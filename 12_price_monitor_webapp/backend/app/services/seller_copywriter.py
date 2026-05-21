"""Seller copywriter service - SEO product description generator."""
from __future__ import annotations


import logging

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.models import Product, SellerCopy

logger = logging.getLogger(__name__)

class SellerCopywriter:
    """Generates SEO-optimized product descriptions for sellers."""

    def __init__(self) -> None:
        self._llm: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._llm is None:
            self._llm = AsyncOpenAI(
                api_key=settings.openai_api_key or "not-set",
                base_url=settings.openai_base_url,
            )
        return self._llm

    async def generate(self, product_id: int, db: AsyncSession) -> dict | None:
        """Generate SEO description for a product."""
        result = await db.execute(
            select(Product)
            .options(selectinload(Product.price_history))
            .where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()
        if not product:
            return None

        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты SEO-копирайтер для маркетплейсов. "
                            "Создавай продающие описания товаров на русском языке. "
                            "Включи ключевые слова для поиска."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Создай SEO-описание для товара:\n"
                            f"Название: {product.name}\n"
                            f"Бренд: {product.brand or 'не указан'}\n"
                            f"Категория: {product.category or 'не указана'}\n\n"
                            f"Верни JSON: {{\"title\": \"...\", \"description\": \"...\", \"keywords\": \"...\"}}"
                        ),
                    },
                ],
                max_tokens=800,
                temperature=0.7,
            )
            content = response.choices[0].message.content or ""

            # Parse response (simple approach)
            import json
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = {
                    "title": product.name,
                    "description": content,
                    "keywords": "",
                }

            # Save to DB
            copy = SellerCopy(
                product_id=product_id,
                title=data.get("title", product.name),
                description=data.get("description", ""),
                keywords=data.get("keywords", ""),
            )
            db.add(copy)
            await db.commit()
            await db.refresh(copy)

            return {
                "id": copy.id,
                "title": copy.title,
                "description": copy.description,
                "keywords": copy.keywords,
            }
        except Exception as e:
            logger.error("Copywriter generation failed: %s", e)
            return None

seller_copywriter = SellerCopywriter()
