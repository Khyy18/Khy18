"""Pydantic v2 schemas for payments."""

from pydantic import BaseModel


class PaymentCreate(BaseModel):
    plan: str
    provider: str


class PaymentResponse(BaseModel):
    confirmation_url: str
    payment_id: str


class WebhookPayload(BaseModel):
    event: str | None = None
    payment_id: str | None = None
    status: str | None = None
