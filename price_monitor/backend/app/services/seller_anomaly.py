"""Seller anomaly detector - identifies suspicious seller behavior."""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PriceHistory, Product, Review

logger = logging.getLogger(__name__)


class SellerAnomalyDetector:
    """Detects suspicious seller patterns based on reviews and pricing."""

    async def analyze_seller(self, product_id: int, db: AsyncSession) -> dict:
        """Analyze a product's seller for suspicious behavior.

        Scoring:
        - All reviews are 5-star: +30
        - Reviews posted on the same day: +30
        - Price significantly below category average: +40

        Returns dict with keys: score (0-100), reasons (list[str]), is_suspicious (bool).
        """
        score = 0
        reasons: list[str] = []

        # Check reviews
        reviews_result = await db.execute(
            select(Review).where(Review.product_id == product_id)
        )
        reviews = reviews_result.scalars().all()

        if reviews:
            # Check if all reviews are 5-star
            ratings = [r.rating for r in reviews if r.rating is not None]
            if ratings and all(r == 5 for r in ratings):
                score += 30
                reasons.append("Все отзывы имеют максимальную оценку 5 звезд")

            # Check if reviews are posted on the same day
            dates = [r.analyzed_at.date() for r in reviews if r.analyzed_at]
            if dates:
                unique_dates = set(dates)
                if len(unique_dates) == 1 and len(dates) >= 3:
                    score += 30
                    reasons.append("Все отзывы оставлены в один день")

        # Check if price is significantly below category average
        product_result = await db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = product_result.scalar_one_or_none()

        if product and product.category:
            # Get latest price for this product
            latest_price_result = await db.execute(
                select(PriceHistory.price)
                .where(PriceHistory.product_id == product_id)
                .order_by(PriceHistory.timestamp.desc())
                .limit(1)
            )
            latest_price_row = latest_price_result.first()

            if latest_price_row:
                product_price = latest_price_row[0]

                # Get average price in same category
                avg_result = await db.execute(
                    select(func.avg(PriceHistory.price))
                    .join(Product, Product.id == PriceHistory.product_id)
                    .where(Product.category == product.category)
                )
                avg_price_row = avg_result.first()

                if avg_price_row and avg_price_row[0]:
                    avg_price = float(avg_price_row[0])
                    if avg_price > 0 and product_price < avg_price * 0.5:
                        score += 40
                        reasons.append(
                            f"Цена ({product_price:.0f}) значительно ниже "
                            f"средней по категории ({avg_price:.0f})"
                        )

        return {
            "score": min(score, 100),
            "reasons": reasons,
            "is_suspicious": score > 70,
        }


seller_anomaly_detector = SellerAnomalyDetector()
