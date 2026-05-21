"""Profile router - user profile and subscription info."""
from __future__ import annotations


from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/profile", tags=["profile"])

@router.get("")
async def get_profile(
    user: User = Depends(get_current_user),
):
    """Get current user profile with subscription info."""

    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "is_vip": user.is_vip,
        "vip_expires_at": user.vip_expires_at.isoformat() if user.vip_expires_at else None,
        "referral_code": user.referral_code,
        "created_at": user.created_at.isoformat(),
    }

@router.put("")
async def update_profile(
    username: str | None = None,
    fcm_token: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update user profile fields."""
    if username is not None:
        user.username = username
    if fcm_token is not None:
        user.fcm_token = fcm_token
    await db.commit()
    await db.refresh(user)
    return {"ok": True}
