"""Pydantic v2 schemas for click tracking."""

from pydantic import BaseModel


class ClickStats(BaseModel):
    short_id: str
    total_clicks: int
    unique_users: int
    conversions: int
    ctr: float
