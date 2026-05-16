"""Pydantic v2 schemas for alerts."""
from __future__ import annotations


from pydantic import BaseModel

class AlertCreate(BaseModel):
    keyword: str
    max_price: float | None = None
    category: str | None = None

class AlertUpdate(BaseModel):
    keyword: str | None = None
    max_price: float | None = None
    category: str | None = None
    is_active: bool | None = None

class AlertOut(BaseModel):
    id: int
    keyword: str
    max_price: float | None
    category: str | None
    is_active: bool
    created_at: str

    model_config = {"from_attributes": True}
