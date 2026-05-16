"""Partners router - partner registration, widget code, stats, payouts."""
from __future__ import annotations


import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Click, Partner, User
from app.db.session import get_db
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/partners", tags=["partners"])

@router.post("/register")
async def register_partner(
    channel_name: str,
    channel_url: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Register as a partner."""

    # Check if already registered
    existing = await db.execute(
        select(Partner).where(Partner.user_id == user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Вы уже зарегистрированы как партнер")

    widget_code = secrets.token_urlsafe(16)
    partner = Partner(
        user_id=user.id,
        channel_name=channel_name,
        channel_url=channel_url,
        widget_code=widget_code,
    )
    db.add(partner)
    await db.commit()
    await db.refresh(partner)

    return {
        "id": partner.id,
        "widget_code": partner.widget_code,
        "commission_percent": partner.commission_percent,
    }

@router.get("/me")
async def get_partner_info(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get partner info and stats."""
    result = await db.execute(
        select(Partner).where(Partner.user_id == user.id)
    )
    partner = result.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=404, detail="Вы не зарегистрированы как партнер")

    return {
        "id": partner.id,
        "channel_name": partner.channel_name,
        "channel_url": partner.channel_url,
        "widget_code": partner.widget_code,
        "commission_percent": partner.commission_percent,
        "total_clicks": partner.total_clicks,
        "total_conversions": partner.total_conversions,
        "balance": partner.balance,
        "is_active": partner.is_active,
    }

@router.get("/stats")
async def get_partner_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get detailed partner statistics."""
    result = await db.execute(
        select(Partner).where(Partner.user_id == user.id)
    )
    partner = result.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=404, detail="Вы не зарегистрированы как партнер")

    # Get recent clicks
    clicks_result = await db.execute(
        select(Click)
        .where(Click.partner_id == partner.id)
        .order_by(Click.timestamp.desc())
        .limit(50)
    )
    clicks = clicks_result.scalars().all()

    conversions = [c for c in clicks if c.converted]

    return {
        "total_clicks": partner.total_clicks,
        "total_conversions": partner.total_conversions,
        "conversion_rate": (
            partner.total_conversions / partner.total_clicks * 100
            if partner.total_clicks > 0
            else 0.0
        ),
        "balance": partner.balance,
        "recent_clicks": len(clicks),
        "recent_conversions": len(conversions),
    }

@router.post("/payout")
async def request_payout(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Request a payout of partner balance."""
    result = await db.execute(
        select(Partner).where(Partner.user_id == user.id)
    )
    partner = result.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=404, detail="Вы не зарегистрированы как партнер")

    if partner.balance < 100.0:
        raise HTTPException(
            status_code=400,
            detail="Минимальная сумма для вывода: 100 руб.",
        )

    payout_amount = partner.balance
    partner.balance = 0.0
    await db.commit()

    return {"payout_amount": payout_amount, "status": "processing"}
