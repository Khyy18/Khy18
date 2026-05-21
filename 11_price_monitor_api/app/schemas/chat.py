"""Pydantic v2 schemas for AI chat."""

from pydantic import BaseModel

from app.schemas.deals import DealOut


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    products: list[DealOut] | None = None
