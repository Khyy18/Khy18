"""Free trial API routes - start, status, and upgrade endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Trial, TrialStatus, User
from dashboard.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trial", tags=["trial"])

TRIAL_DURATION_DAYS = 7
TRIAL_LEADS_LIMIT = 50
TRIAL_EMAILS_LIMIT = 100
TRIAL_VOICE_CALLS_LIMIT = 5


async def check_trial_limits(
    tenant_id: uuid.UUID,
    session: AsyncSession,
    resource: str = "leads",
) -> None:
    """Check if trial limits are exceeded. Raises HTTPException 403 if limit reached.

    Args:
        tenant_id: The tenant to check.
        session: Database session.
        resource: One of 'leads', 'emails', 'linkedin', 'voice'.

    Raises:
        HTTPException: 403 if trial limit exceeded or resource not allowed.
    """
    result = await session.execute(
        select(Trial).where(Trial.tenant_id == tenant_id)
    )
    trial = result.scalar_one_or_none()

    if trial is None or trial.status != TrialStatus.active:
        return

    if resource == "linkedin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="LinkedIn not available during trial",
        )

    if resource == "leads" and trial.leads_used >= TRIAL_LEADS_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trial leads limit reached",
        )

    if resource == "emails" and trial.emails_used >= TRIAL_EMAILS_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trial emails limit reached",
        )

    if resource == "voice":
        voice_used = getattr(trial, "voice_calls_used", 0) or 0
        if voice_used >= TRIAL_VOICE_CALLS_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Trial voice calls limit reached",
            )


async def _get_session():
    """Lazy wrapper around core.db.get_session."""
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


@router.post("/start")
async def start_trial(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Create a 7-day free trial for the current user's tenant.

    Limits: 50 leads, 100 emails, 5 voice calls. No credit card required.
    """
    # Check if trial already exists
    result = await session.execute(
        select(Trial).where(Trial.tenant_id == current_user.tenant_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Trial already exists for this tenant",
        )

    now = datetime.now(timezone.utc)
    trial = Trial(
        tenant_id=current_user.tenant_id,
        status=TrialStatus.active,
        started_at=now,
        ends_at=now + timedelta(days=TRIAL_DURATION_DAYS),
        leads_used=0,
        emails_used=0,
    )
    session.add(trial)
    await session.flush()
    await session.refresh(trial)

    return {
        "id": str(trial.id),
        "tenant_id": str(trial.tenant_id),
        "status": trial.status.value,
        "started_at": trial.started_at.isoformat(),
        "ends_at": trial.ends_at.isoformat(),
        "leads_limit": TRIAL_LEADS_LIMIT,
        "emails_limit": TRIAL_EMAILS_LIMIT,
        "voice_calls_limit": TRIAL_VOICE_CALLS_LIMIT,
        "leads_used": trial.leads_used,
        "emails_used": trial.emails_used,
    }


@router.get("/status")
async def get_trial_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get trial status with days remaining, usage, and conversion prompts.

    Auto-freezes trial if 7 days have elapsed. Shows conversion prompts
    at day 5 and day 3.
    """
    result = await session.execute(
        select(Trial).where(Trial.tenant_id == current_user.tenant_id)
    )
    trial = result.scalar_one_or_none()
    if trial is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No trial found for this tenant",
        )

    now = datetime.now(timezone.utc)

    # Auto-freeze if trial has expired
    if trial.status == TrialStatus.active and now >= trial.ends_at:
        trial.status = TrialStatus.frozen
        await session.flush()

    days_elapsed = (now - trial.started_at).days
    days_remaining = max(0, (trial.ends_at - now).days)

    # Conversion prompts at day 5 and day 3
    conversion_prompt: str | None = None
    if trial.status == TrialStatus.active:
        if days_elapsed >= 5:
            conversion_prompt = "Your trial ends in 2 days! Upgrade now to keep your data and continue growing."
        elif days_elapsed >= 3:
            conversion_prompt = "You're halfway through your trial. Upgrade to unlock unlimited leads and emails."

    return {
        "id": str(trial.id),
        "status": trial.status.value,
        "days_remaining": days_remaining,
        "leads_used": trial.leads_used,
        "leads_limit": TRIAL_LEADS_LIMIT,
        "emails_used": trial.emails_used,
        "emails_limit": TRIAL_EMAILS_LIMIT,
        "is_frozen": trial.status == TrialStatus.frozen,
        "conversion_prompt": conversion_prompt,
        "started_at": trial.started_at.isoformat(),
        "ends_at": trial.ends_at.isoformat(),
    }


@router.post("/upgrade")
async def upgrade_trial(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Mark the trial as converted and return redirect URL to billing.

    After conversion, the tenant should select a paid plan via the billing page.
    """
    result = await session.execute(
        select(Trial).where(Trial.tenant_id == current_user.tenant_id)
    )
    trial = result.scalar_one_or_none()
    if trial is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No trial found for this tenant",
        )

    if trial.status == TrialStatus.converted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Trial already converted",
        )

    trial.status = TrialStatus.converted
    trial.converted_at = datetime.now(timezone.utc)
    await session.flush()

    return {
        "status": "converted",
        "redirect_url": "/billing",
    }
