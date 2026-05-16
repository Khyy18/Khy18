"""Niche detector service - detect trending niches by category growth."""
from __future__ import annotations


import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NicheAnalysis, PriceHistory, Product

logger = logging.getLogger(__name__)

class NicheDetector:
    """Detects trending niches by analyzing category growth patterns."""

    async def analyze(self, db: AsyncSession, days: int = 7) -> list[dict]:
        """Analyze category growth over the specified period."""
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Get product counts per category (recent vs older)
        recent_query = (
            select(Product.category, func.count(Product.id).label("count"))
            .where(Product.created_at >= cutoff)
            .where(Product.category.isnot(None))
            .group_by(Product.category)
        )
        total_query = (
            select(Product.category, func.count(Product.id).label("count"))
            .where(Product.category.isnot(None))
            .group_by(Product.category)
        )

        recent_result = await db.execute(recent_query)
        total_result = await db.execute(total_query)

        recent_counts = {row.category: row.count for row in recent_result.all()}
        total_counts = {row.category: row.count for row in total_result.all()}

        # Calculate growth
        results = []
        for category, total in total_counts.items():
            recent = recent_counts.get(category, 0)
            if total == 0:
                continue
            growth_percent = (recent / total) * 100

            # Get average price in category
            avg_price_result = await db.execute(
                select(func.avg(PriceHistory.price))
                .join(Product, PriceHistory.product_id == Product.id)
                .where(Product.category == category)
            )
            avg_price = avg_price_result.scalar() or 0.0

            results.append({
                "category": category,
                "growth_percent": round(growth_percent, 1),
                "product_count": total,
                "avg_price": round(avg_price, 0),
            })

        # Sort by growth
        results.sort(key=lambda x: x["growth_percent"], reverse=True)
        top_results = results[:20]

        # Save to DB
        for r in top_results:
            analysis = NicheAnalysis(
                category=r["category"],
                growth_percent=r["growth_percent"],
                avg_price=r["avg_price"],
                product_count=r["product_count"],
            )
            db.add(analysis)
        await db.commit()

        return top_results

niche_detector = NicheDetector()
