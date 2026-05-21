"""Price forecast service using time-series analysis (no numpy)."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PriceHistory

logger = logging.getLogger(__name__)


@dataclass
class ForecastResult:
    """Result of price forecast analysis."""

    trend: str  # 'falling', 'rising', 'stable'
    recommendation: str  # 'wait', 'buy_now', 'neutral'
    confidence: float  # 0.0 - 1.0
    reasoning: str  # Russian explanation


class PriceForecastService:
    """Price forecast service using MA and linear regression."""

    async def forecast(self, product_id: int, db: AsyncSession) -> ForecastResult | None:
        """Forecast price trend for a product based on last 90 days of history.

        Returns ForecastResult or None if insufficient data.
        """
        cutoff = datetime.utcnow() - timedelta(days=90)
        result = await db.execute(
            select(PriceHistory)
            .where(PriceHistory.product_id == product_id)
            .where(PriceHistory.timestamp >= cutoff)
            .order_by(PriceHistory.timestamp)
        )
        records = list(result.scalars().all())

        if len(records) < 3:
            return None

        prices = [r.price for r in records]
        timestamps = [r.timestamp for r in records]

        ma7 = self._moving_average(prices, 7)
        ma30 = self._moving_average(prices, 30)

        slope = self._linear_slope(prices)
        seasonality = self._day_of_week_factor(records)

        trend = self._determine_trend(slope, ma7, ma30)
        recommendation = self._determine_recommendation(trend, prices, seasonality)
        confidence = self._calculate_confidence(len(records), slope, prices)
        reasoning = self._generate_reasoning(trend, recommendation, prices, timestamps)

        return ForecastResult(
            trend=trend,
            recommendation=recommendation,
            confidence=confidence,
            reasoning=reasoning,
        )

    def _moving_average(self, prices: list[float], window: int) -> float:
        """Calculate moving average for the last N values."""
        if len(prices) < window:
            window = len(prices)
        subset = prices[-window:]
        return sum(subset) / len(subset)

    def _linear_slope(self, prices: list[float]) -> float:
        """Calculate linear trend slope via least-squares (no numpy).

        Uses the formula: slope = (n*sum(x*y) - sum(x)*sum(y)) / (n*sum(x^2) - sum(x)^2)
        """
        n = len(prices)
        if n < 2:
            return 0.0

        sum_x = 0.0
        sum_y = 0.0
        sum_xy = 0.0
        sum_x2 = 0.0

        for i, price in enumerate(prices):
            x = float(i)
            sum_x += x
            sum_y += price
            sum_xy += x * price
            sum_x2 += x * x

        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return 0.0

        return (n * sum_xy - sum_x * sum_y) / denominator

    def _day_of_week_factor(self, records: list[PriceHistory]) -> dict[int, float]:
        """Calculate average price factor per day of week."""
        day_prices: dict[int, list[float]] = {i: [] for i in range(7)}
        for r in records:
            day_prices[r.timestamp.weekday()].append(r.price)

        overall_avg = sum(r.price for r in records) / len(records)
        factors = {}
        for day, prices in day_prices.items():
            if prices:
                factors[day] = (sum(prices) / len(prices)) / overall_avg
            else:
                factors[day] = 1.0
        return factors

    def _determine_trend(self, slope: float, ma7: float, ma30: float) -> str:
        """Determine price trend."""
        if ma30 == 0:
            threshold = 0.0
        else:
            threshold = ma30 * 0.01  # 1% of ma30

        if slope < -threshold:
            return "falling"
        elif slope > threshold:
            return "rising"
        return "stable"

    def _determine_recommendation(
        self, trend: str, prices: list[float], seasonality: dict[int, float]
    ) -> str:
        """Determine buy recommendation."""
        current = prices[-1]
        min_price = min(prices)
        avg_price = sum(prices) / len(prices)

        # If current price is near historical minimum, recommend buying
        if min_price > 0 and current <= min_price * 1.05:
            return "buy_now"

        if trend == "falling":
            return "wait"
        elif trend == "rising" and current < avg_price:
            return "buy_now"

        return "neutral"

    def _calculate_confidence(
        self, data_points: int, slope: float, prices: list[float]
    ) -> float:
        """Calculate confidence score based on data availability and consistency."""
        # Base confidence from data quantity
        data_score = min(data_points / 30.0, 1.0)

        # Consistency: how well a linear fit describes the data
        avg_price = sum(prices) / len(prices)
        if avg_price == 0:
            return round(data_score * 0.5, 2)

        slope_strength = min(abs(slope) / avg_price * 100, 1.0)

        confidence = data_score * 0.6 + slope_strength * 0.4
        return round(min(max(confidence, 0.0), 1.0), 2)

    def _generate_reasoning(
        self,
        trend: str,
        recommendation: str,
        prices: list[float],
        timestamps: list[datetime],
    ) -> str:
        """Generate Russian-language reasoning text."""
        current = prices[-1]
        min_price = min(prices)

        if recommendation == "buy_now" and current <= min_price * 1.05:
            return "Исторический минимум, бери сейчас"

        if trend == "falling":
            # Check how long it's been falling
            falling_days = 0
            for i in range(len(prices) - 1, 0, -1):
                if prices[i] < prices[i - 1]:
                    falling_days += 1
                else:
                    break
            if falling_days >= 14:
                return "Цена снижается последние 2 недели"
            elif falling_days >= 7:
                return "Цена снижается последнюю неделю, стоит подождать"
            return "Наблюдается тренд на снижение цены"

        if trend == "rising":
            return "Цена растёт, если нужен товар - лучше купить сейчас"

        return "Цена стабильна, можно покупать в любой момент"
