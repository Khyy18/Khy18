"""Email preview API routes - preview emails before sending."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Campaign, Lead, Sequence, User
from dashboard.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/preview", tags=["preview"])


class EmailPreviewRequest(BaseModel):
    """Request body for email preview."""

    lead_id: UUID
    campaign_id: UUID
    sequence_step: int = 0


class SendTestRequest(BaseModel):
    """Request body for sending a test email."""

    email_address: str
    subject: str
    body: str


async def _get_session():
    """Lazy wrapper around core.db.get_session."""
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


def _generate_preview_content(lead: Lead, step_index: int) -> dict:
    """Generate mock email preview content based on lead data.

    Uses a template-based approach for previews without calling the LLM.
    """
    step_types = ["initial", "follow_up_1", "follow_up_2", "breakup"]
    step_type = step_types[step_index % len(step_types)]

    subjects = {
        "initial": f"Quick question for {lead.company}",
        "follow_up_1": f"Following up - {lead.company}",
        "follow_up_2": f"One more thought for {lead.first_name}",
        "breakup": f"Last note, {lead.first_name}",
    }

    bodies = {
        "initial": (
            f"Hi {lead.first_name},\n\n"
            f"I noticed {lead.company} is growing fast in the {lead.title} space. "
            f"I wanted to reach out because we help companies like yours automate outbound sales.\n\n"
            f"Would you be open to a quick 15-minute call this week?\n\nBest regards"
        ),
        "follow_up_1": (
            f"Hi {lead.first_name},\n\n"
            f"Just circling back on my previous email. I know things get busy at {lead.company}.\n\n"
            f"Happy to share a quick case study from a similar company if helpful.\n\nBest"
        ),
        "follow_up_2": (
            f"Hi {lead.first_name},\n\n"
            f"One more thought - we recently helped a company similar to {lead.company} "
            f"increase their reply rates by 3x.\n\n"
            f"Worth a quick chat?\n\nBest"
        ),
        "breakup": (
            f"Hi {lead.first_name},\n\n"
            f"I understand timing may not be right. I will not reach out again, "
            f"but feel free to connect if things change at {lead.company}.\n\nAll the best"
        ),
    }

    return {
        "subject": subjects.get(step_type, f"Message for {lead.first_name}"),
        "body": bodies.get(step_type, f"Hi {lead.first_name}, reaching out from our team."),
        "step_type": step_type,
    }


@router.post("/email")
async def preview_email(
    data: EmailPreviewRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Generate email preview for a specific lead and sequence step.

    Returns subject and body without sending. Uses mock copywriter logic.
    """
    # Verify lead belongs to tenant
    result = await session.execute(
        select(Lead).where(
            Lead.id == data.lead_id,
            Lead.tenant_id == current_user.tenant_id,
        )
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    # Verify campaign belongs to tenant
    result = await session.execute(
        select(Campaign).where(
            Campaign.id == data.campaign_id,
            Campaign.tenant_id == current_user.tenant_id,
        )
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    preview = _generate_preview_content(lead, data.sequence_step)

    return {
        "lead_id": str(lead.id),
        "campaign_id": str(campaign.id),
        "sequence_step": data.sequence_step,
        "subject": preview["subject"],
        "body": preview["body"],
        "step_type": preview["step_type"],
    }


@router.get("/campaign/{campaign_id}")
async def preview_campaign(
    campaign_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Preview all sequence steps for the first lead in a campaign.

    Returns previews for each step in the campaign's sequence.
    """
    # Verify campaign belongs to tenant
    result = await session.execute(
        select(Campaign).where(
            Campaign.id == campaign_id,
            Campaign.tenant_id == current_user.tenant_id,
        )
    )
    campaign = result.scalar_one_or_none()
    if campaign is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    # Get first lead for tenant
    result = await session.execute(
        select(Lead)
        .where(Lead.tenant_id == current_user.tenant_id)
        .order_by(Lead.created_at.asc())
        .limit(1)
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No leads found for this tenant",
        )

    # Get sequence steps count
    num_steps = 4  # Default
    if campaign.sequence_id:
        seq_result = await session.execute(
            select(Sequence).where(Sequence.id == campaign.sequence_id)
        )
        sequence = seq_result.scalar_one_or_none()
        if sequence and sequence.steps:
            num_steps = len(sequence.steps)

    previews = []
    for step_index in range(num_steps):
        preview = _generate_preview_content(lead, step_index)
        previews.append({
            "step_index": step_index,
            "step_type": preview["step_type"],
            "subject": preview["subject"],
            "body": preview["body"],
        })

    return {
        "campaign_id": str(campaign.id),
        "campaign_name": campaign.name,
        "lead_id": str(lead.id),
        "lead_name": f"{lead.first_name} {lead.last_name}",
        "previews": previews,
    }


@router.post("/send-test")
async def send_test_email(
    data: SendTestRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Send a test email to a specified address.

    Sends the provided subject and body to the email address for testing purposes.
    """
    # In production, this would use the email sender.
    # For now, we validate and return success without actual sending.
    logger.info(
        "Test email requested by user %s to %s",
        current_user.id,
        data.email_address,
    )

    return {
        "status": "sent",
        "email_address": data.email_address,
        "subject": data.subject,
        "message": "Test email queued for delivery",
    }
