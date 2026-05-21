"""Dynamic pricing service - optimal price recommendations for sellers."""
from __future__ import annotations


import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import PriceHistory, Product

logger = logging.getLogger(__name__)

@dataclass
class PriceRecommendation:
    product_id: int
    current_price: float
    recommended_price: float
    min_market_price: float
    max_market_price: float
    avg_market_price: float
    reasoning: str

class DynamicPricingService:
    """Generates optimal price recommendations based on market data."""

    async def recommend(
        self, product_id: int, db: AsyncSession
    ) -> PriceRecommendation | None:
        """Generate price recommendation for a product."""
        result = await db.execute(
            select(Product)
            .options(selectinload(Product.price_history))
            .where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()
        if not product or not product.price_history:
            return None

        current_price = sorted(
            product.price_history, key=lambda p: p.timestamp, reverse=True
        )[0].price

        # Get market prices for similar products in same category
        market_query = (
            select(
                func.min(PriceHistory.price),
                func.max(PriceHistory.price),
                func.avg(PriceHistory.price),
            )
            .join(Product, PriceHistory.product_id == Product.id)
            .where(Product.category == product.category)
            .where(Product.id != product.id)
        )
        market_result = await db.execute(market_query)
        row = market_result.one()
        min_price = row[0] or current_price
        max_price = row[1] or current_price
        avg_price = row[2] or current_price

        # Simple recommendation: slightly below average for competitiveness
        recommended = round(avg_price * 0.95, 0)
        if recommended < min_price:
            recommended = min_price

        reasoning = (
            f"Средняя цена в категории: {avg_price:.0f} руб. "
            f"Рекомендуем: {recommended:.0f} руб. (на 5% ниже средней для конкурентности)"
        )

        return PriceRecommendation(
            product_id=product_id,
            current_price=current_price,
            recommended_price=recommended,
            min_market_price=min_price,
            max_market_price=max_price,
            avg_market_price=avg_price,
            reasoning=reasoning,
        )

dynamic_pricing_service = DynamicPricingService()
