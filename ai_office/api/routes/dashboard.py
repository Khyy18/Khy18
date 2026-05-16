"""Эндпоинт дашборда с метриками."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import DashboardResponse
from ai_office.core.database import get_session
from ai_office.core.models import ActivityLog, Agent, Task, TokenUsage

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    session: AsyncSession = Depends(get_session),
):
    """Агрегированные метрики для дашборда.

    Uses GROUP BY queries to minimize DB round-trips (~5-7 total queries
    instead of ~48 sequential per-day/per-hour queries).
    """
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=6)

    # Tasks today (1 query)
    tasks_today_result = await session.execute(
        select(func.count(Task.id)).where(Task.created_at >= today_start)
    )
    tasks_today = tasks_today_result.scalar() or 0

    # Tasks week history - single GROUP BY query
    date_col = func.date(Task.created_at)
    tasks_week_result = await session.execute(
        select(date_col.label("day"), func.count(Task.id))
        .where(Task.created_at >= week_start)
        .group_by(date_col)
    )
    tasks_by_day = {str(row[0]): row[1] for row in tasks_week_result.all()}

    tasks_week_history = []
    for i in range(6, -1, -1):
        day = (today_start - timedelta(days=i)).strftime("%Y-%m-%d")
        tasks_week_history.append(tasks_by_day.get(day, 0))

    # Cost today (1 query)
    cost_today_result = await session.execute(
        select(func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0.0)).where(
            TokenUsage.timestamp >= today_start
        )
    )
    cost_today = float(cost_today_result.scalar() or 0.0)

    # Cost week history - single GROUP BY query
    cost_date_col = func.date(TokenUsage.timestamp)
    cost_week_result = await session.execute(
        select(cost_date_col.label("day"), func.sum(TokenUsage.estimated_cost_usd))
        .where(TokenUsage.timestamp >= week_start)
        .group_by(cost_date_col)
    )
    cost_by_day = {str(row[0]): float(row[1] or 0.0) for row in cost_week_result.all()}

    cost_week_history = []
    for i in range(6, -1, -1):
        day = (today_start - timedelta(days=i)).strftime("%Y-%m-%d")
        cost_week_history.append(cost_by_day.get(day, 0.0))

    # NOTE: avg_response_ms and response_time_history are estimated/synthetic values.
    # They are derived from activity density (not actual measured latency).
    # The response_time_estimated=True field in the response indicates this.
    avg_response_ms = 350

    # Response time history - single GROUP BY query for activity counts per day
    activity_date_col = func.date(ActivityLog.timestamp)
    activity_week_result = await session.execute(
        select(activity_date_col.label("day"), func.count(ActivityLog.id))
        .where(ActivityLog.timestamp >= week_start)
        .group_by(activity_date_col)
    )
    activity_by_day = {str(row[0]): row[1] for row in activity_week_result.all()}

    response_time_history = []
    for i in range(6, -1, -1):
        day = (today_start - timedelta(days=i)).strftime("%Y-%m-%d")
        count = activity_by_day.get(day, 0)
        response_time_history.append(max(200, 350 + count * 10))

    # Active agents (1 query)
    active_agents_result = await session.execute(
        select(func.count(Agent.id)).where(Agent.status != "idle")
    )
    active_agents = active_agents_result.scalar() or 0

    # Hourly activity (last 24 hours) - single GROUP BY query using strftime for SQLite
    hour_col = literal_column("strftime('%H', timestamp)")
    hourly_result = await session.execute(
        select(hour_col.label("hour"), func.count(ActivityLog.id))
        .where(ActivityLog.timestamp >= now - timedelta(hours=24))
        .group_by(hour_col)
    )
    activity_by_hour = {int(row[0]): row[1] for row in hourly_result.all()}

    # Build 24-element array ordered from oldest to newest
    hourly_activity = []
    for i in range(23, -1, -1):
        target_hour = (now - timedelta(hours=i + 1)).hour
        hourly_activity.append(activity_by_hour.get(target_hour, 0))

    return DashboardResponse(
        tasks_today=tasks_today,
        tasks_week_history=tasks_week_history,
        cost_today=cost_today,
        cost_week_history=cost_week_history,
        avg_response_ms=avg_response_ms,
        response_time_history=response_time_history,
        response_time_estimated=True,
        active_agents=active_agents,
        hourly_activity=hourly_activity,
    )
