"""Pydantic v2 schemas for categories (matches mobile app Category type)."""

from pydantic import BaseModel


class CategoryOut(BaseModel):
    id: str
    name: str
    icon: str
    productCount: int

    model_config = {"from_attributes": True}
