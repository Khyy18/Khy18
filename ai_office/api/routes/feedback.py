"""Эндпоинты для обратной связи."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import FeedbackCreate, FeedbackResponse, FeedbackStatsResponse
from ai_office.core.database import get_session
from ai_office.core.models import Feedback

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse, status_code=201)
async def create_feedback(
    data: FeedbackCreate,
    session: AsyncSession = Depends(get_session),
):
    """Создать запись обратной связи."""
    feedback = Feedback(
        user_telegram_id=data.user_telegram_id,
        agent_name=data.agent_name,
        message_id=data.message_id,
        rating=data.rating,
        is_positive=data.is_positive,
        comment=data.comment,
    )
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)
    return feedback


@router.get("/stats", response_model=List[FeedbackStatsResponse])
async def get_feedback_stats(
    session: AsyncSession = Depends(get_session),
):
    """Получить статистику обратной связи по агентам."""
    query = select(
        Feedback.agent_name,
        func.avg(Feedback.rating).label("avg_rating"),
        func.count(Feedback.id).label("total_count"),
        func.sum(
            case((Feedback.is_positive == True, 1), else_=0)  # noqa: E712
        ).label("positive_count"),
        func.sum(
            case((Feedback.is_positive != None, 1), else_=0)  # noqa: E711
        ).label("has_positive_count"),
    ).group_by(Feedback.agent_name)

    result = await session.execute(query)
    rows = result.all()

    stats = []
    for row in rows:
        total_with_positive = row.has_positive_count or 0
        positive_pct = 0.0
        if total_with_positive > 0:
            positive_pct = (row.positive_count / total_with_positive) * 100

        stats.append(
            FeedbackStatsResponse(
                agent_name=row.agent_name,
                avg_rating=round(row.avg_rating, 2) if row.avg_rating else None,
                total_count=row.total_count,
                positive_percentage=round(positive_pct, 1),
            )
        )

    return stats
