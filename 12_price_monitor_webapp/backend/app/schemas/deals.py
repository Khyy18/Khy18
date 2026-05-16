"""Pydantic v2 schemas for deals/products."""
from __future__ import annotations


from pydantic import BaseModel

class PricePointOut(BaseModel):
    date: str
    price: float

class ForecastOut(BaseModel):
    trend: str
    recommendation: str
    confidence: float
    reasoning: str

class DealOut(BaseModel):
    id: str
    title: str
    image: str
    currentPrice: float
    oldPrice: float
    discount: float
    category: str
    marketplace: str
    priceHistory: list[PricePointOut] = []
    rating: float = 0.0
    reviewsSummary: str = ""
    affiliateUrl: str = ""
    forecast: ForecastOut | None = None

class DealListResponse(BaseModel):
    products: list[DealOut]
    total: int
    hasMore: bool
