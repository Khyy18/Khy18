"""Эндпоинты для Growth-аналитики: churn detection, upsell stats, engagement."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import (
    ChurnRiskResponse,
    EngagementScoreResponse,
    UpsellStatsResponse,
)
from ai_office.core.churn_detection import (
    calculate_engagement,
    detect_churning_workspaces,
)
from ai_office.core.database import get_session
from ai_office.core.upsell import get_upsell_stats

router = APIRouter(prefix="/api/admin", tags=["admin", "growth"])


@router.get("/churn", response_model=List[ChurnRiskResponse])
async def list_churn_risk(
    session: AsyncSession = Depends(get_session),
):
    """Получить список workspace с риском оттока (неактивны 3+ дней)."""
    at_risk = await detect_churning_workspaces(session)
    return [ChurnRiskResponse(**item) for item in at_risk]


@router.get("/upsell/stats", response_model=UpsellStatsResponse)
async def upsell_stats(
    session: AsyncSession = Depends(get_session),
):
    """Получить статистику upsell-конверсий."""
    stats = await get_upsell_stats(session)
    return UpsellStatsResponse(**stats)


@router.get("/engagement/{workspace_id}", response_model=EngagementScoreResponse)
async def engagement_score(
    workspace_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Получить оценку вовлечённости конкретного workspace."""
    score = await calculate_engagement(workspace_id, session)
    return EngagementScoreResponse(
        workspace_id=workspace_id,
        messages_per_day=score.messages_per_day,
        tasks_created=score.tasks_created,
        tasks_completed=score.tasks_completed,
        agents_used=score.agents_used,
        score=score.score,
    )
