"""Tracking router - short link redirects and click stats."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.services.tracking_service import TrackingService

router = APIRouter(tags=["tracking"])


@router.get("/go/{short_id}")
async def redirect_short_link(
    short_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Redirect to the affiliate URL and record a click."""
    link_data = TrackingService.resolve_short_link(short_id)
    if not link_data:
        raise HTTPException(status_code=404, detail="Link not found")

    service = TrackingService(db)
    await service.record_click(
        short_id=short_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return RedirectResponse(url=link_data["affiliate_url"], status_code=302)


@router.get("/admin/tracking/stats")
async def get_tracking_stats(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Get click tracking statistics (auth required)."""
    service = TrackingService(db)
    stats = await service.get_stats()
    return {"stats": stats}
