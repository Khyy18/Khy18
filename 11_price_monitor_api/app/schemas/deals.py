"""Pydantic v2 schemas for deals (matches mobile app Product type)."""

from pydantic import BaseModel


class PricePointOut(BaseModel):
    date: str
    price: float


class DealOut(BaseModel):
    id: str
    title: str
    image: str
    currentPrice: float
    oldPrice: float
    discount: float
    category: str
    marketplace: str
    priceHistory: list[PricePointOut]
    rating: float
    reviewsSummary: str
    affiliateUrl: str
    forecast: str | None = None

    model_config = {"from_attributes": True}


class DealListResponse(BaseModel):
    products: list[DealOut]
    total: int
    hasMore: bool
