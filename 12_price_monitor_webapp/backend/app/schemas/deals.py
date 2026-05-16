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
    image_url: str
    current_price: float
    original_price: float
    discount_percent: float
    marketplace: str
    category_id: str
    category_name: str
    url: str
    price_history: list[PricePointOut] = []
    is_favorite: bool = False
    created_at: str = ""
    rating: float = 0.0
    reviews_summary: str = ""
    forecast: ForecastOut | None = None

class DealListResponse(BaseModel):
    items: list[DealOut]
    total: int
    page: int
    has_next: bool
