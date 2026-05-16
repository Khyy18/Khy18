"""Эндпоинты для мониторинга SLA."""

from fastapi import APIRouter, Depends
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import SLAStatusResponse
from ai_office.core.database import get_session
from ai_office.core.models import Task
from ai_office.core.sla import sla_engine

router = APIRouter(prefix="/api/sla", tags=["sla"])


@router.get("/status", response_model=SLAStatusResponse)
async def get_sla_status(
    session: AsyncSession = Depends(get_session),
):
    """Получить текущий статус SLA."""
    status = await sla_engine.get_sla_status(session)

    # Count total monitored tasks
    result = await session.execute(
        select(sa_func.count(Task.id)).where(Task.sla_target_seconds.isnot(None))
    )
    total_monitored = result.scalar() or 0

    return SLAStatusResponse(
        compliance_percent=status["compliance_percent"],
        avg_response_by_priority=status["avg_response_by_priority"],
        breaches_count=status["breaches_count"],
        total_monitored=total_monitored,
    )
