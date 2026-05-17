"""Calendar integration API routes - connect providers and check availability."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.models import Tenant, User
from dashboard.auth import get_current_user
from integrations.calendar import CalendarManager, GoogleCalendarClient

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


@router.get("/callback")
async def calendar_oauth_callback(
    code: str = Query(..., description="OAuth authorization code from Google"),
    state: str = Query("", description="State parameter containing tenant_id"),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Handle Google OAuth2 callback by exchanging code for tokens and storing them.

    Google redirects here after user authorizes. We exchange the code for
    access/refresh tokens and persist them in the tenant's calendar_config
    JSONB field.
    """
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code",
        )

    # Validate tenant_id from state
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing state parameter",
        )

    try:
        tenant_id = uuid.UUID(state)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter",
        )

    # Exchange authorization code for tokens
    google_client = GoogleCalendarClient(
        client_id=settings.google_calendar_client_id,
        client_secret=settings.google_calendar_client_secret,
    )
    token_data = await google_client.exchange_code(code)

    if "error" in token_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth token exchange failed: {token_data['error']}",
        )

    # Persist tokens in the tenant's calendar_config JSONB field
    result = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    calendar_config = getattr(tenant, "calendar_config", None) or {}
    calendar_config["provider"] = "google"
    calendar_config["access_token"] = token_data.get("access_token", "")
    calendar_config["refresh_token"] = token_data.get("refresh_token", "")
    calendar_config["token_type"] = token_data.get("token_type", "Bearer")
    calendar_config["expires_in"] = token_data.get("expires_in", 3600)
    tenant.calendar_config = calendar_config
    await session.flush()

    return {
        "status": "connected",
        "provider": "google",
        "tenant_id": str(tenant_id),
    }


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

    # Load tokens from DB if using Google provider
    if manager.provider == "google":
        result = await session.execute(
            select(Tenant).where(Tenant.id == current_user.tenant_id)
        )
        tenant = result.scalar_one_or_none()
        if tenant:
            cal_config = getattr(tenant, "calendar_config", None) or {}
            if cal_config.get("access_token"):
                manager.set_google_tokens(
                    access_token=cal_config["access_token"],
                    refresh_token=cal_config.get("refresh_token"),
                )

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
