"""Pydantic v2 schemas for payments."""
from __future__ import annotations


from pydantic import BaseModel

class PaymentCreate(BaseModel):
    plan: str
    provider: str = "yukassa"

class PaymentOut(BaseModel):
    id: int
    amount: float
    currency: str
    status: str
    plan: str | None
    provider: str
    created_at: str

    model_config = {"from_attributes": True}

class PaymentConfirm(BaseModel):
    provider_payment_id: str

class TelegramStarsPayment(BaseModel):
    plan: str
    stars_amount: int
