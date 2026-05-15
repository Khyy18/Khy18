"""Эндпоинты для работы с агентами."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import AgentResponse
from ai_office.core.database import get_session
from ai_office.core.models import Agent

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("", response_model=List[AgentResponse])
async def list_agents(session: AsyncSession = Depends(get_session)):
    """Получить список всех агентов с их статусами."""
    result = await session.execute(select(Agent))
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
