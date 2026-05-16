"""Personal digest service - product recommendations based on user activity."""
from __future__ import annotations

import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Click, Favorite, PriceHistory, Product

logger = logging.getLogger(__name__)


class DigestService:
    """Generates personalized product digests based on user behavior."""

    async def generate_digest(self, user_id: int, db: AsyncSession) -> list[dict]:
        """Analyze user activity and return top discount products matching interests.

        Returns up to 5 product recommendations as list of dicts with keys:
        product_id, name, category, current_price, discount_percent, image_url.
        """
        # Gather user's preferred categories from clicks and favorites
        categories = await self._get_user_categories(user_id, db)

        # Find products with the highest discounts in preferred categories
        query = (
            select(Product, PriceHistory)
            .join(PriceHistory, PriceHistory.product_id == Product.id)
            .where(PriceHistory.discount_percent.isnot(None))
            .where(PriceHistory.discount_percent > 0)
            .order_by(PriceHistory.discount_percent.desc())
        )

        if categories:
            query = query.where(Product.category.in_(categories))

        # Get latest price per product using subquery for most recent entry
        query = query.limit(20)

        result = await db.execute(query)
        rows = result.all()

        # Deduplicate by product_id and take top 5
        seen_ids: set[int] = set()
        recommendations: list[dict] = []

        for product, price_entry in rows:
            if product.id in seen_ids:
                continue
            seen_ids.add(product.id)
            recommendations.append({
                "product_id": product.id,
                "name": product.name,
                "category": product.category or "",
                "current_price": price_entry.price,
                "discount_percent": price_entry.discount_percent,
                "image_url": product.image_url or "",
            })
            if len(recommendations) >= 5:
                break

        return recommendations

    async def _get_user_categories(self, user_id: int, db: AsyncSession) -> list[str]:
        """Extract preferred categories from user's click and favorite history."""
        # Categories from clicks
        click_cats = await db.execute(
            select(Product.category)
            .join(Click, Click.product_id == Product.id)
            .where(Click.user_id == user_id)
            .where(Product.category.isnot(None))
            .group_by(Product.category)
            .order_by(func.count(Click.id).desc())
            .limit(5)
        )
        categories = [row[0] for row in click_cats.all() if row[0]]

        # Categories from favorites
        fav_cats = await db.execute(
            select(Product.category)
            .join(Favorite, Favorite.product_id == Product.id)
            .where(Favorite.user_id == user_id)
            .where(Product.category.isnot(None))
            .group_by(Product.category)
            .order_by(func.count(Favorite.id).desc())
            .limit(5)
        )
        for row in fav_cats.all():
            if row[0] and row[0] not in categories:
                categories.append(row[0])

        return categories


digest_service = DigestService()
