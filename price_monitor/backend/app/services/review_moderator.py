"""Review moderator service - NLP classifier for fake reviews."""
from __future__ import annotations


import logging

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Review

logger = logging.getLogger(__name__)

class ReviewModerator:
    """Detects fake reviews using NLP classification."""

    def __init__(self) -> None:
        self._llm: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._llm is None:
            self._llm = AsyncOpenAI(
                api_key=settings.openai_api_key or "not-set",
                base_url=settings.openai_base_url,
            )
        return self._llm

    async def analyze_review(self, review_id: int, db: AsyncSession) -> dict:
        """Analyze a single review for authenticity."""
        result = await db.execute(select(Review).where(Review.id == review_id))
        review = result.scalar_one_or_none()
        if not review:
            return {"error": "Отзыв не найден"}

        score = await self._classify(review.text)
        review.fake_score = score
        review.is_fake = score > 0.7
        await db.commit()

        return {
            "review_id": review.id,
            "fake_score": score,
            "is_fake": review.is_fake,
        }

    async def _classify(self, text: str) -> float:
        """Classify review text and return fake probability (0.0 - 1.0)."""
        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты эксперт по выявлению фейковых отзывов. "
                            "Оцени вероятность того, что отзыв фейковый (0.0 - 1.0). "
                            "Отвечай только числом."
                        ),
                    },
                    {"role": "user", "content": f"Отзыв: {text[:500]}"},
                ],
                max_tokens=10,
                temperature=0.1,
            )
            content = response.choices[0].message.content or "0.5"
            return min(1.0, max(0.0, float(content.strip())))
        except Exception as e:
            logger.error("Review classification failed: %s", e)
            return 0.5

    async def batch_analyze(self, product_id: int, db: AsyncSession) -> list[dict]:
        """Analyze all reviews for a product."""
        result = await db.execute(
            select(Review).where(Review.product_id == product_id)
        )
        reviews = result.scalars().all()

        results = []
        for review in reviews:
            score = await self._classify(review.text)
            review.fake_score = score
            review.is_fake = score > 0.7
            results.append({
                "review_id": review.id,
                "fake_score": score,
                "is_fake": review.is_fake,
            })

        await db.commit()
        return results

review_moderator = ReviewModerator()
