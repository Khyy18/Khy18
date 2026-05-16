"""Публичные эндпоинты для демонстрации (без аутентификации)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import PublicAgentResponse, PublicActivityResponse
from ai_office.core.database import get_session
from ai_office.core.models import ActivityLog, Agent, Workspace

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/{workspace_id}/agents", response_model=list[PublicAgentResponse])
async def get_public_agents(
    workspace_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Получить список агентов публичного workspace."""
    result = await session.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if workspace is None or not workspace.is_public:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found or not public",
        )

    # DEMO: Возвращаем всех агентов системы, а не только привязанных к workspace.
    # Это демо-эндпоинт для PublicDemo landing page - показывает полный каталог
    # агентов "карманной компании". В production фильтровать по workspace_id.
    agents_result = await session.execute(select(Agent))
    agents = agents_result.scalars().all()
    return [
        PublicAgentResponse(name=a.name, role=a.role, status=a.status)
        for a in agents
    ]


@router.get("/{workspace_id}/activity", response_model=list[PublicActivityResponse])
async def get_public_activity(
    workspace_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Получить последние 20 записей активности публичного workspace."""
    result = await session.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if workspace is None or not workspace.is_public:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found or not public",
        )

    logs_result = await session.execute(
        select(ActivityLog)
        .where(ActivityLog.workspace_id == workspace_id)
        .order_by(ActivityLog.timestamp.desc())
        .limit(20)
    )
    logs = logs_result.scalars().all()
    return [
        PublicActivityResponse(
            agent_name=log.agent.name if log.agent else "Unknown",
            action_type=log.action_type,
            action_description=log.action_description,
            timestamp=log.timestamp,
        )
        for log in logs
    ]
