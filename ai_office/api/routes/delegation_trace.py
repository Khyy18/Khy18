"""Эндпоинты для трассировки делегирований."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import DelegationTraceResponse
from ai_office.core.database import get_session
from ai_office.core.models import DelegationTrace

router = APIRouter(prefix="/api/delegations", tags=["delegations"])


@router.get("/{trace_id}/trace", response_model=DelegationTraceResponse)
async def get_delegation_trace(
    trace_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Получить трассировку делегирования по ID."""
    result = await session.execute(
        select(DelegationTrace).where(DelegationTrace.id == trace_id)
    )
    trace = result.scalar_one_or_none()
    if not trace:
        raise HTTPException(status_code=404, detail="Трассировка не найдена")

    messages = json.loads(trace.messages_json)

    return DelegationTraceResponse(
        id=trace.id,
        source_agent=trace.source_agent,
        target_agent=trace.target_agent,
        task_id=trace.task_id,
        messages=messages,
        created_at=trace.created_at,
    )
