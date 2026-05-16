"""Эндпоинты для управления запросами на одобрение."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import ApprovalRequestResponse, ApprovalResolveRequest
from ai_office.core.database import get_session
from ai_office.core.models import ApprovalRequest
from ai_office.core.approval import approval_manager

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalRequestResponse])
async def list_approvals(
    status: Optional[str] = Query(default=None, description="Фильтр по статусу"),
    session: AsyncSession = Depends(get_session),
):
    """Получить список запросов на одобрение."""
    query = select(ApprovalRequest)
    if status:
        query = query.where(ApprovalRequest.status == status)
    query = query.order_by(ApprovalRequest.requested_at.desc())
    result = await session.execute(query)
    items = result.scalars().all()
    return [ApprovalRequestResponse.model_validate(item) for item in items]


@router.get("/{request_id}", response_model=ApprovalRequestResponse)
async def get_approval(
    request_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Получить запрос на одобрение по ID."""
    result = await session.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == request_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    return ApprovalRequestResponse.model_validate(item)


@router.post("", response_model=ApprovalRequestResponse, status_code=201)
async def create_approval(
    agent_name: str = Query(...),
    action_type: str = Query(...),
    description: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """Создать запрос на одобрение."""
    request_id = await approval_manager.request_approval(
        session=session,
        agent_name=agent_name,
        action_type=action_type,
        description=description,
    )
    result = await session.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == request_id)
    )
    item = result.scalar_one()
    return ApprovalRequestResponse.model_validate(item)


@router.post("/{request_id}/resolve", response_model=ApprovalRequestResponse)
async def resolve_approval(
    request_id: int,
    body: ApprovalResolveRequest,
    session: AsyncSession = Depends(get_session),
):
    """Одобрить или отклонить запрос."""
    result = await session.execute(
        select(ApprovalRequest).where(ApprovalRequest.id == request_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Запрос не найден")

    await approval_manager.handle_callback(
        session=session,
        request_id=request_id,
        approved=body.approved,
        user_id=body.user_id,
    )

    await session.refresh(item)
    return ApprovalRequestResponse.model_validate(item)
