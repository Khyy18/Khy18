"""Эндпоинты для лога активности."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import ActivityResponse, PaginatedResponse
from ai_office.core.database import get_session
from ai_office.core.models import ActivityLog

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("", response_model=PaginatedResponse[ActivityResponse])
async def list_activity(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """Получить лог последних действий с пагинацией."""
    # Общее количество
    count_query = select(func.count(ActivityLog.id))
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Результаты с пагинацией, сортировка по времени (новые первые)
    query = (
        select(ActivityLog)
        .order_by(ActivityLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(query)
    logs = result.scalars().all()

    items = []
    for log in logs:
        items.append(
            ActivityResponse(
                id=log.id,
                agent_id=log.agent_id,
                agent_name=log.agent.name if log.agent else None,
                action_type=log.action_type,
                action_description=log.action_description,
                timestamp=log.timestamp,
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
