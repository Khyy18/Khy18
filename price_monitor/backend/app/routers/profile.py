"""Profile router - user profile and subscription info."""
from __future__ import annotations


from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Badge, User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.services.gamification import gamification_service

router = APIRouter(prefix="/profile", tags=["profile"])

@router.get("")
async def get_profile(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get current user profile with subscription info."""
    # Check and award any newly earned badges
    await gamification_service.check_and_award_badges(user.id, db)

    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "is_vip": user.is_vip,
        "vip_expires_at": user.vip_expires_at.isoformat() if user.vip_expires_at else None,
        "referral_code": user.referral_code,
        "created_at": user.created_at.isoformat(),
    }

@router.get("/badges")
async def get_badges(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get all badges earned by the current user."""
    result = await db.execute(
        select(Badge)
        .where(Badge.user_id == user.id)
        .order_by(Badge.earned_at.desc())
    )
    badges = result.scalars().all()
    return [
        {
            "id": b.id,
            "badge_type": b.badge_type,
            "title": b.title,
            "description": b.description,
            "icon": b.icon,
            "earned_at": b.earned_at.isoformat() if b.earned_at else None,
        }
        for b in badges
    ]

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
