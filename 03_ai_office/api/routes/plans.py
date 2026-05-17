"""Эндпоинты для работы с планами."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ai_office.api.dependencies import get_current_user_optional, get_tenant_id
from ai_office.api.schemas import PlanResponse
from ai_office.core.database import get_session
from ai_office.core.models import Plan, User

router = APIRouter(prefix="/api/plans", tags=["plans"])


@router.get("", response_model=List[PlanResponse])
async def list_plans(
    session: AsyncSession = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Получить список всех планов с их шагами."""
    tenant_id = get_tenant_id(current_user)

    query = select(Plan).options(selectinload(Plan.steps)).order_by(Plan.created_at.desc())
    if tenant_id is not None:
        query = query.where(Plan.tenant_id == tenant_id)

    result = await session.execute(query)
    plans = result.scalars().all()
    return plans


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Получить план по ID с его шагами."""
    tenant_id = get_tenant_id(current_user)

    query = select(Plan).options(selectinload(Plan.steps)).where(Plan.id == plan_id)
    if tenant_id is not None:
        query = query.where(Plan.tenant_id == tenant_id)

    result = await session.execute(query)
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="План не найден")
    return plan
