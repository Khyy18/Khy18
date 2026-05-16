"""Pydantic v2 schemas for arbitrage."""
from __future__ import annotations


from pydantic import BaseModel

class ArbitrageResultOut(BaseModel):
    id: int
    product_name: str
    brand: str | None
    price_wb: float
    price_ozon: float
    diff_percent: float
    match_score: float
    found_at: str

    model_config = {"from_attributes": True}

class ArbitrageListResponse(BaseModel):
    results: list[ArbitrageResultOut]
    total: int

class ArbitrageSearchRequest(BaseModel):
    category: str | None = None
    min_diff_percent: float = 5.0
    limit: int = 20
