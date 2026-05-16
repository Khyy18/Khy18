"""Эндпоинты для работы с планами."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_office.api.schemas import PlanResponse
from ai_office.core.database import get_session
from ai_office.core.models import Plan

router = APIRouter(prefix="/api/plans", tags=["plans"])


@router.get("", response_model=List[PlanResponse])
async def list_plans(session: AsyncSession = Depends(get_session)):
    """Получить список всех планов с их шагами."""
    query = select(Plan).options(selectinload(Plan.steps)).order_by(Plan.created_at.desc())
    result = await session.execute(query)
    plans = result.scalars().all()
    return plans


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(plan_id: int, session: AsyncSession = Depends(get_session)):
    """Получить план по ID с его шагами."""
    query = select(Plan).options(selectinload(Plan.steps)).where(Plan.id == plan_id)
    result = await session.execute(query)
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="План не найден")
    return plan
