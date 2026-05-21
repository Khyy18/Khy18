"""Price forecast service - price trend prediction."""
from __future__ import annotations


import logging
from dataclasses import dataclass

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.models import PriceHistory, Product

logger = logging.getLogger(__name__)

@dataclass
class ForecastResult:
    trend: str
    recommendation: str
    confidence: float
    reasoning: str

class PriceForecastService:
    """Predicts price trends using historical data and LLM analysis."""

    def __init__(self) -> None:
        self._llm: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if self._llm is None:
            self._llm = AsyncOpenAI(
                api_key=settings.openai_api_key or "not-set",
                base_url=settings.openai_base_url,
            )
        return self._llm

    async def forecast(self, product_id: int, db: AsyncSession) -> ForecastResult | None:
        """Generate price forecast for a product."""
        result = await db.execute(
            select(Product)
            .options(selectinload(Product.price_history))
            .where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()
        if not product or not product.price_history:
            return None

        prices = sorted(product.price_history, key=lambda p: p.timestamp)
        if len(prices) < 3:
            return ForecastResult(
                trend="stable",
                recommendation="Недостаточно данных для прогноза",
                confidence=0.3,
                reasoning="Менее 3 точек данных",
            )

        # Simple trend analysis
        recent = [p.price for p in prices[-5:]]
        if recent[-1] < recent[0] * 0.9:
            trend = "falling"
            recommendation = "Цена снижается. Можно подождать ещё."
        elif recent[-1] > recent[0] * 1.1:
            trend = "rising"
            recommendation = "Цена растёт. Рекомендуем покупать сейчас."
        else:
            trend = "stable"
            recommendation = "Цена стабильна."

        return ForecastResult(
            trend=trend,
            recommendation=recommendation,
            confidence=0.7,
            reasoning=f"Анализ {len(prices)} точек данных за период",
        )

price_forecast_service = PriceForecastService()
