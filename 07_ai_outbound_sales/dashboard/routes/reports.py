"""Weekly reports API routes."""

from __future__ import annotations

import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Tenant, User
from dashboard.auth import get_current_user
from integrations.weekly_report import WeeklyReportGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


async def _get_session() -> AsyncGenerator[AsyncSession, None]:
    """Lazy wrapper around core.db.get_session to avoid import-time engine creation."""
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


class ReportPreferencesRequest(BaseModel):
    delivery_method: str  # 'email' | 'telegram' | 'both'
    email_address: str | None = None
    telegram_chat_id: str | None = None


class ReportPreferencesResponse(BaseModel):
    delivery_method: str | None = None
    email_address: str | None = None
    telegram_chat_id: str | None = None


@router.get("/weekly")
async def get_weekly_report(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Generate weekly report on-demand for the current user's tenant.

    Returns JSON with all metrics, delta percentages, and delivery status.
    """
    tenant_id = current_user.tenant_id
    generator = WeeklyReportGenerator()

    report_data = await generator.generate_report(tenant_id, session)

    # Check if preferences are configured and deliver
    result = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()

    delivery_status = {"delivered_via": [], "success": False}
    if tenant:
        settings_data = tenant.settings or {}
        preferences = settings_data.get("report_preferences", {})
        if preferences:
            delivery_status = await generator.deliver_report(
                tenant_id, report_data, session
            )

    report_data["delivery_status"] = delivery_status
    return report_data


@router.put("/weekly/preferences")
async def update_report_preferences(
    data: ReportPreferencesRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Update report delivery preferences for the current tenant."""
    if data.delivery_method not in ("email", "telegram", "both"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="delivery_method must be 'email', 'telegram', or 'both'",
        )

    tenant_id = current_user.tenant_id
    result = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    settings_data = dict(tenant.settings or {})
    settings_data["report_preferences"] = {
        "delivery_method": data.delivery_method,
        "email_address": data.email_address or "",
        "telegram_chat_id": data.telegram_chat_id or "",
    }
    tenant.settings = settings_data
    await session.commit()

    return {"status": "ok", "preferences": settings_data["report_preferences"]}


@router.get("/weekly/preferences", response_model=ReportPreferencesResponse)
async def get_report_preferences(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get current report delivery preferences for the tenant."""
    tenant_id = current_user.tenant_id
    result = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    settings_data = tenant.settings or {}
    preferences = settings_data.get("report_preferences", {})

    return {
        "delivery_method": preferences.get("delivery_method"),
        "email_address": preferences.get("email_address"),
        "telegram_chat_id": preferences.get("telegram_chat_id"),
    }
