"""Pydantic v2 schemas for alerts (matches mobile app Alert type)."""

from pydantic import BaseModel


class AlertCreate(BaseModel):
    keyword: str
    maxPrice: float | None = None
    category: str | None = None


class AlertOut(BaseModel):
    id: str
    keyword: str
    maxPrice: float | None = None
    category: str
    active: bool
    createdAt: str

    model_config = {"from_attributes": True}


class AlertToggle(BaseModel):
    active: bool
