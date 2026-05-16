"""Эндпоинты для работы с делегированиями."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_office.api.schemas import ActivityResponse
from ai_office.core.database import get_session
from ai_office.core.models import ActivityLog

router = APIRouter(prefix="/api/delegations", tags=["delegations"])


@router.get("", response_model=List[ActivityResponse])
async def list_delegations(session: AsyncSession = Depends(get_session)):
    """Получить последние делегирования (task_delegated события)."""
    query = (
        select(ActivityLog)
        .options(selectinload(ActivityLog.agent))
        .where(ActivityLog.action_type == "task_delegated")
        .order_by(ActivityLog.timestamp.desc())
        .limit(50)
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

    return items
