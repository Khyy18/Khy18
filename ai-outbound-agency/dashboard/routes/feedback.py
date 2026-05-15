"""Feedback summary API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import LeadFeedback, User
from dashboard.auth import get_current_user

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


async def _get_session():
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


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
