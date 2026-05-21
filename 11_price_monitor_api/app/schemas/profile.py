"""Pydantic v2 schemas for user profile (matches mobile app UserProfile type)."""

from pydantic import BaseModel


class ProfileOut(BaseModel):
    id: str
    name: str
    email: str
    subscription: str
    referralCode: str
    totalSaved: float
    dealsTracked: int
    bestDeal: float

    model_config = {"from_attributes": True}


class AuthRequest(BaseModel):
    telegram_id: int
    username: str | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
