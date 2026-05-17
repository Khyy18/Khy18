"""Эндпоинты для работы с агентами."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_office.api.dependencies import get_current_user_optional, get_tenant_id
from ai_office.api.rate_limit import check_rate_limit
from ai_office.api.schemas import ActivityResponse, AgentResponse, PaginatedResponse, TaskResponse
from ai_office.core.database import get_session
from ai_office.core.models import ActivityLog, Agent, Task, TenantAgent, User

router = APIRouter(prefix="/api/agents", tags=["agents"], dependencies=[Depends(check_rate_limit)])


@router.get("", response_model=List[AgentResponse])
async def list_agents(
    session: AsyncSession = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Получить список всех агентов с их статусами."""
    tenant_id = get_tenant_id(current_user)

    if tenant_id is not None:
        # Get enabled agent names for this tenant
        ta_query = select(TenantAgent.agent_name).where(
            TenantAgent.tenant_id == tenant_id,
            TenantAgent.is_enabled == True,  # noqa: E712
        )
        ta_result = await session.execute(ta_query)
        enabled_names = [row[0] for row in ta_result.all()]

        if enabled_names:
            query = select(Agent).where(Agent.name.in_(enabled_names))
        else:
            # If no TenantAgent records, show all agents (backward compat)
            query = select(Agent)
    else:
        query = select(Agent)

    result = await session.execute(query)
    agents = result.scalars().all()
    return agents


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: int, session: AsyncSession = Depends(get_session)):
    """Получить информацию об агенте по ID."""
    result = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Агент не найден")
    return agent


@router.get("/{agent_id}/activity", response_model=PaginatedResponse[ActivityResponse])
async def get_agent_activity(
    agent_id: int,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Получить лог активности конкретного агента."""
    tenant_id = get_tenant_id(current_user)

    # Проверяем существование агента
    agent_result = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Агент не найден")

    # Общее количество записей для этого агента
    count_query = select(func.count(ActivityLog.id)).where(ActivityLog.agent_id == agent_id)
    if tenant_id is not None:
        count_query = count_query.where(ActivityLog.tenant_id == tenant_id)
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Записи с пагинацией
    query = (
        select(ActivityLog)
        .options(selectinload(ActivityLog.agent))
        .where(ActivityLog.agent_id == agent_id)
        .order_by(ActivityLog.timestamp.desc())
        .offset(offset)
        .limit(limit)
    )
    if tenant_id is not None:
        query = query.where(ActivityLog.tenant_id == tenant_id)

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


@router.get("/{agent_id}/tasks", response_model=List[TaskResponse])
async def get_agent_tasks(
    agent_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Получить задачи, назначенные конкретному агенту."""
    tenant_id = get_tenant_id(current_user)

    # Проверяем существование агента
    agent_result = await session.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Агент не найден")

    query = select(Task).where(Task.executor_id == agent_id).order_by(Task.created_at.desc())
    if tenant_id is not None:
        query = query.where(Task.tenant_id == tenant_id)

    result = await session.execute(query)
    tasks = result.scalars().all()
    return tasks
