"""Pydantic v2 schemas for admin panel."""
from __future__ import annotations


from pydantic import BaseModel

class StatsOut(BaseModel):
    total_users: int
    vip_users: int
    total_products: int
    total_alerts: int
    total_clicks: int
    total_revenue: float

class UserAdminOut(BaseModel):
    id: int
    telegram_id: int
    username: str | None
    is_vip: bool
    created_at: str

    model_config = {"from_attributes": True}

class PostCreate(BaseModel):
    product_id: int
    channel_id: int
    text: str
    variant: str | None = None

class PostOut(BaseModel):
    id: int
    product_id: int
    channel_id: int
    text: str
    variant: str | None
    impressions: int
    clicks: int
    ctr: float
    published_at: str

    model_config = {"from_attributes": True}

class ParserStatusOut(BaseModel):
    name: str
    status: str
    last_run: str | None
    products_count: int

class SettingUpdate(BaseModel):
    key: str
    value: str
