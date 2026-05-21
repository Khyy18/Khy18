"""Profile and auth router."""

import secrets

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, Favorite, User
from app.db.session import get_db
from app.middleware.auth import (
    _check_rate_limit,
    create_access_token,
    get_current_user,
)
from app.schemas.profile import AuthRequest, AuthResponse, ProfileOut

router = APIRouter(tags=["profile"])


@router.post("/auth/register", response_model=AuthResponse)
async def register_or_login(
    data: AuthRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user or login existing by telegram_id. Returns JWT.

    Rate limited to prevent enumeration attacks on telegram_id.
    """
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)
    result = await db.execute(
        select(User).where(User.telegram_id == data.telegram_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            telegram_id=data.telegram_id,
            username=data.username,
            referral_code=secrets.token_urlsafe(8),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    return AuthResponse(access_token=token)


@router.get("/profile", response_model=ProfileOut)
async def get_profile(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get current user profile with subscription info and stats."""
    # Count tracked deals (favorites count)
    fav_result = await db.execute(
        select(func.count(Favorite.id)).where(Favorite.user_id == user.id)
    )
    deals_tracked = fav_result.scalar() or 0

    return ProfileOut(
        id=str(user.id),
        name=user.username or f"User {user.telegram_id}",
        email="",
        subscription="vip" if user.is_vip else "free",
        referralCode=user.referral_code or "",
        totalSaved=0.0,
        dealsTracked=deals_tracked,
        bestDeal=0.0,
    )


class FcmTokenRequest(BaseModel):
    token: str


@router.post("/profile/fcm-token")
async def save_fcm_token(
    data: FcmTokenRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Save user's FCM token for push notifications."""
    user.fcm_token = data.token
    await db.commit()
    return {"status": "ok"}
