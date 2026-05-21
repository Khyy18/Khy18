"""Tracking router - click tracking with short links."""
from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Click, ShortLink, User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.services.tracking_service import tracking_service

router = APIRouter(prefix="/tracking", tags=["tracking"])

@router.get("/go/{short_id}")
async def redirect_short_link(
    short_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Track click and return affiliate URL."""

    result = await db.execute(
        select(ShortLink).where(ShortLink.short_id == short_id)
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")

    # Record click
    click = Click(
        short_id=short_id,
        product_id=link.product_id,
        partner_id=link.partner_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(click)
    await db.commit()

    return {"url": link.affiliate_url}

@router.post("/create-link")
async def create_short_link(
    product_id: int,
    affiliate_url: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a short tracking link."""
    link = await tracking_service.create_short_link(
        product_id=product_id,
        affiliate_url=affiliate_url,
        db=db,
    )
    return {"short_id": link.short_id, "url": f"/tracking/go/{link.short_id}"}

@router.post("/convert/{short_id}")
async def mark_conversion(
    short_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Mark a click as converted."""
    await tracking_service.mark_conversion(short_id=short_id, db=db)
    return {"ok": True}
