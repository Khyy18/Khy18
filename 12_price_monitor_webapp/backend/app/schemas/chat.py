"""Pydantic v2 schemas for chatbot."""
from __future__ import annotations


from pydantic import BaseModel

class ChatMessageIn(BaseModel):
    message: str

class ChatMessageOut(BaseModel):
    role: str
    content: str
    created_at: str

    model_config = {"from_attributes": True}

class ChatResponse(BaseModel):
    reply: str
    product_ids: list[int] = []
