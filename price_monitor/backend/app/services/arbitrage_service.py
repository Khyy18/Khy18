"""Arbitrage service - fuzzy match products across marketplaces, compare prices."""
from __future__ import annotations


import logging
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ArbitrageResult, PriceHistory, Product

logger = logging.getLogger(__name__)

class ArbitrageService:
    """Compares prices on WB vs Ozon using fuzzy matching by name/brand."""

    MIN_MATCH_SCORE = 0.6

    def _match_score(self, product_a: Product, product_b: Product) -> float:
        """Calculate match score between two products using fuzzy matching."""
        name_score = SequenceMatcher(
            None, product_a.name.lower(), product_b.name.lower()
        ).ratio()

        brand_score = 0.0
        if product_a.brand and product_b.brand:
            brand_score = SequenceMatcher(
                None, product_a.brand.lower(), product_b.brand.lower()
            ).ratio()

        # Weighted combination: name is more important
        if product_a.brand and product_b.brand:
            return name_score * 0.7 + brand_score * 0.3
        return name_score

    def _get_latest_price(self, product: Product) -> float | None:
        """Get latest price for a product."""
        if not product.price_history:
            return None
        latest = sorted(product.price_history, key=lambda p: p.timestamp, reverse=True)[0]
        return latest.price

    async def scan(
        self,
        category: str | None,
        min_diff_percent: float,
        limit: int,
        db: AsyncSession,
    ) -> int:
        """Scan for price arbitrage opportunities between WB and Ozon."""
        # Get WB products
        wb_query = (
            select(Product)
            .options(selectinload(Product.price_history))
            .where(Product.marketplace == "wb")
        )
        if category:
            wb_query = wb_query.where(Product.category == category)
        wb_query = wb_query.limit(200)

        # Get Ozon products
        ozon_query = (
            select(Product)
            .options(selectinload(Product.price_history))
            .where(Product.marketplace == "ozon")
        )
        if category:
            ozon_query = ozon_query.where(Product.category == category)
        ozon_query = ozon_query.limit(200)

        wb_result = await db.execute(wb_query)
        ozon_result = await db.execute(ozon_query)

        wb_products = list(wb_result.scalars().all())
        ozon_products = list(ozon_result.scalars().all())

        found = 0
        for wb_product in wb_products:
            wb_price = self._get_latest_price(wb_product)
            if not wb_price:
                continue

            for ozon_product in ozon_products:
                score = self._match_score(wb_product, ozon_product)
                if score < self.MIN_MATCH_SCORE:
                    continue

                ozon_price = self._get_latest_price(ozon_product)
                if not ozon_price:
                    continue

                # Calculate price difference
                if wb_price == 0 or ozon_price == 0:
                    continue
                diff_percent = abs(wb_price - ozon_price) / min(wb_price, ozon_price) * 100

                if diff_percent >= min_diff_percent:
                    arb = ArbitrageResult(
                        product_wb_id=wb_product.id,
                        product_ozon_id=ozon_product.id,
                        product_name=wb_product.name,
                        brand=wb_product.brand,
                        price_wb=wb_price,
                        price_ozon=ozon_price,
                        diff_percent=round(diff_percent, 2),
                        match_score=round(score, 3),
                    )
                    db.add(arb)
                    found += 1

                    if found >= limit:
                        break
            if found >= limit:
                break

        await db.commit()
        return found

arbitrage_service = ArbitrageService()
