"""Feedback summary API endpoints."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import LeadFeedback, User
from dashboard.auth import get_current_user

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


async def _get_session():
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


class FeedbackCreateRequest(BaseModel):
    """Schema for creating feedback via POST."""

    lead_id: UUID
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    feedback_type: str = "general"
    event_trigger: str = "manual"


@router.post("/")
async def create_feedback(
    payload: FeedbackCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Submit feedback for a lead.

    Accepts {lead_id, rating, comment?, feedback_type?, event_trigger?} and stores
    the feedback record via FeedbackCollector.
    """
    from core.db import async_session_factory
    from core.config import settings
    from agents.feedback_collector import FeedbackCollector

    collector = FeedbackCollector(
        session_factory=async_session_factory,
        settings=settings,
    )
    feedback = await collector.collect_feedback(
        lead_id=payload.lead_id,
        tenant_id=current_user.tenant_id,
        rating=payload.rating,
        comment=payload.comment,
        feedback_type=payload.feedback_type,
        event_trigger=payload.event_trigger,
    )
    return {
        "id": str(feedback.id),
        "lead_id": str(feedback.lead_id),
        "tenant_id": str(feedback.tenant_id),
        "rating": feedback.rating,
        "comment": feedback.comment,
        "feedback_type": feedback.feedback_type,
        "event_trigger": feedback.event_trigger,
        "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
    }


@router.get("/summary")
async def get_feedback_summary(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Return aggregated feedback stats for the current tenant."""
    tenant_id = current_user.tenant_id

    # Average rating
    avg_result = await session.execute(
        select(func.avg(LeadFeedback.rating)).where(
            LeadFeedback.tenant_id == tenant_id,
        )
    )
    average_rating = avg_result.scalar() or 0.0

    # Total count
    count_result = await session.execute(
        select(func.count(LeadFeedback.id)).where(
            LeadFeedback.tenant_id == tenant_id,
        )
    )
    total_count = count_result.scalar() or 0

    # Rating distribution
    dist_result = await session.execute(
        select(LeadFeedback.rating, func.count(LeadFeedback.id)).where(
            LeadFeedback.tenant_id == tenant_id,
        ).group_by(LeadFeedback.rating)
    )
    rating_distribution = {str(row[0]): row[1] for row in dist_result.all()}

    # Recent comments (last 10)
    comments_result = await session.execute(
        select(LeadFeedback.comment, LeadFeedback.rating, LeadFeedback.created_at)
        .where(
            LeadFeedback.tenant_id == tenant_id,
            LeadFeedback.comment.isnot(None),
        )
        .order_by(LeadFeedback.created_at.desc())
        .limit(10)
    )
    recent_comments = [
        {
            "comment": row[0],
            "rating": row[1],
            "created_at": row[2].isoformat() if row[2] else None,
        }
        for row in comments_result.all()
    ]

    return {
        "average_rating": round(float(average_rating), 2),
        "total_count": total_count,
        "rating_distribution": rating_distribution,
        "recent_comments": recent_comments,
    }
