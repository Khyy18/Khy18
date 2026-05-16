"""Referral system API routes - code generation, stats, and application."""

from __future__ import annotations

import logging
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Referral, User
from dashboard.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/referral", tags=["referral"])


class ApplyReferralRequest(BaseModel):
    """Request body for applying a referral code."""

    code: str


async def _get_session():
    """Lazy wrapper around core.db.get_session."""
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


def _generate_referral_code() -> str:
    """Generate a 6-character alphanumeric referral code."""
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(6))


@router.get("/code")
async def get_or_create_referral_code(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get or create a unique referral code for the current tenant.

    Returns the existing code if one already exists, otherwise generates
    a new 6-character alphanumeric code.
    """
    # Check if tenant already has a referral code
    result = await session.execute(
        select(Referral).where(
            Referral.referrer_tenant_id == current_user.tenant_id,
            Referral.referred_tenant_id.is_(None),
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        return {
            "code": existing.code,
            "created_at": existing.created_at.isoformat() if existing.created_at else None,
        }

    # Generate unique code
    for _ in range(10):
        code = _generate_referral_code()
        check = await session.execute(
            select(Referral).where(Referral.code == code)
        )
        if check.scalar_one_or_none() is None:
            break
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate unique referral code",
        )

    referral = Referral(
        referrer_tenant_id=current_user.tenant_id,
        referred_tenant_id=None,
        code=code,
        reward_applied=False,
    )
    session.add(referral)
    await session.flush()
    await session.refresh(referral)

    return {
        "code": referral.code,
        "created_at": referral.created_at.isoformat() if referral.created_at else None,
    }


@router.get("/stats")
async def get_referral_stats(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get referral statistics for the current tenant.

    Returns total referrals, rewards earned, and pending referrals.
    """
    # Count total referrals (where this tenant is the referrer and someone signed up)
    total_result = await session.execute(
        select(func.count(Referral.id)).where(
            Referral.referrer_tenant_id == current_user.tenant_id,
            Referral.referred_tenant_id.isnot(None),
        )
    )
    total_referrals = total_result.scalar() or 0

    # Count rewards earned
    rewards_result = await session.execute(
        select(func.count(Referral.id)).where(
            Referral.referrer_tenant_id == current_user.tenant_id,
            Referral.reward_applied.is_(True),
        )
    )
    rewards_earned = rewards_result.scalar() or 0

    # Count pending (referred but reward not applied)
    pending_result = await session.execute(
        select(func.count(Referral.id)).where(
            Referral.referrer_tenant_id == current_user.tenant_id,
            Referral.referred_tenant_id.isnot(None),
            Referral.reward_applied.is_(False),
        )
    )
    pending_referrals = pending_result.scalar() or 0

    return {
        "total_referrals": total_referrals,
        "rewards_earned": rewards_earned,
        "pending_referrals": pending_referrals,
    }


@router.post("/apply")
async def apply_referral_code(
    data: ApplyReferralRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Apply a referral code during signup/trial.

    Validates the code exists, is not already used, and the user is not
    applying their own code. Links the referred tenant and marks the reward.
    """
    # Find the referral by code
    result = await session.execute(
        select(Referral).where(Referral.code == data.code)
    )
    referral = result.scalar_one_or_none()

    if referral is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Referral code not found",
        )

    # Cannot apply own code
    if referral.referrer_tenant_id == current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot apply your own referral code",
        )

    # Check if code is already used
    if referral.referred_tenant_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Referral code already used",
        )

    # Apply the referral
    referral.referred_tenant_id = current_user.tenant_id
    referral.reward_applied = True
    await session.flush()

    return {
        "status": "applied",
        "code": referral.code,
        "reward": "1 month free for referrer, 20% off first month for you",
    }
