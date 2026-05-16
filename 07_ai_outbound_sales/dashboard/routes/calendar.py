"""Calendar integration API routes - connect providers and check availability."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.models import User
from dashboard.auth import get_current_user
from integrations.calendar import CalendarManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations/calendar", tags=["calendar"])


async def _get_session():
    """Lazy wrapper around core.db.get_session."""
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


class ConnectRequest(BaseModel):
    """Request body for calendar connection."""

    provider: str  # "calcom", "google", or "calendly"
    api_key: str | None = None  # For Cal.com or Calendly


def _get_calendar_manager(provider: str | None = None) -> CalendarManager:
    """Build a CalendarManager for the given or default provider."""
    prov = provider or settings.calendar_provider
    return CalendarManager(
        provider=prov,
        calcom_api_key=settings.calcom_api_key,
        calcom_base_url=settings.calcom_base_url,
        google_client_id=settings.google_calendar_client_id,
        google_client_secret=settings.google_calendar_client_secret,
        calendly_api_key=settings.calendly_api_key,
        calendly_event_type=settings.calendly_event_type,
    )


@router.post("/connect")
async def connect_calendar(
    body: ConnectRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Initiate a calendar provider connection.

    For Google Calendar, returns an OAuth URL the frontend should redirect to.
    For Cal.com and Calendly, validates that the API key is present and returns success.
    """
    provider = body.provider.lower()

    if provider == "google":
        manager = _get_calendar_manager(provider="google")
        oauth_url = manager.get_oauth_url(state=str(current_user.tenant_id))
        if not oauth_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google Calendar client_id/client_secret not configured",
            )
        return {
            "status": "oauth_required",
            "oauth_url": oauth_url,
            "provider": "google",
        }

    elif provider in ("calcom", "calendly"):
        manager = _get_calendar_manager(provider=provider)
        if not manager.validate_api_key():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{provider} API key not configured",
            )
        return {
            "status": "connected",
            "provider": provider,
        }

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported calendar provider: {provider}",
    )


@router.get("/availability")
async def get_availability(
    start_date: str = Query(..., description="ISO format start date"),
    end_date: str = Query(..., description="ISO format end date"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Check available time slots from the configured calendar provider.

    Returns available slots between start_date and end_date.
    """
    manager = _get_calendar_manager()

    if not manager.validate_api_key():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Calendar provider not configured. Please connect a calendar first.",
        )

    slots = await manager.check_availability(start_date, end_date)
    return {
        "provider": manager.provider,
        "start_date": start_date,
        "end_date": end_date,
        "slots": slots,
    }
