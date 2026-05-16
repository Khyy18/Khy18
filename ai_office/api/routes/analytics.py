"""Эндпоинты для аналитики."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.api.schemas import (
    AgentAnalyticsResponse,
    AnalyticsOverviewResponse,
    ProductivityResponse,
)
from ai_office.core.database import get_session
from ai_office.core.models import Agent, DelegationTrace, Feedback, Task

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview", response_model=AnalyticsOverviewResponse)
async def analytics_overview(
    session: AsyncSession = Depends(get_session),
):
    """Обзор аналитики: KPI за неделю/месяц."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Tasks completed this week
    result = await session.execute(
        select(sa_func.count(Task.id)).where(
            Task.status.in_(["done", "closed"]),
            Task.closed_at >= week_ago,
        )
    )
    tasks_completed_week = result.scalar() or 0

    # Tasks completed this month
    result = await session.execute(
        select(sa_func.count(Task.id)).where(
            Task.status.in_(["done", "closed"]),
            Task.closed_at >= month_ago,
        )
    )
    tasks_completed_month = result.scalar() or 0

    # Avg time to resolve grouped by priority
    result = await session.execute(
        select(Task).where(
            Task.status.in_(["done", "closed"]),
            Task.closed_at.isnot(None),
        )
    )
    completed_tasks = result.scalars().all()

    priority_times: dict[str, list[float]] = {}
    for task in completed_tasks:
        created = task.created_at
        closed = task.closed_at
        if created and closed:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if closed.tzinfo is None:
                closed = closed.replace(tzinfo=timezone.utc)
            seconds = (closed - created).total_seconds()
            priority = task.priority or "medium"
            if priority not in priority_times:
                priority_times[priority] = []
            priority_times[priority].append(seconds)

    avg_time_to_resolve = {}
    for priority, times in priority_times.items():
        if times:
            avg_time_to_resolve[priority] = round(sum(times) / len(times), 1)

    # Agent workload (count tasks per executor)
    result = await session.execute(
        select(Agent.name, sa_func.count(Task.id))
        .join(Task, Task.executor_id == Agent.id, isouter=True)
        .where(Task.status.in_(["open", "in_progress"]))
        .group_by(Agent.name)
    )
    agent_workload = [
        {"agent": row[0], "tasks": row[1]} for row in result.all()
    ]

    # Bottleneck agent (most in-progress tasks)
    bottleneck_agent = None
    if agent_workload:
        bottleneck = max(agent_workload, key=lambda x: x["tasks"])
        bottleneck_agent = bottleneck["agent"]

    # Throughput trend (tasks closed per day for last 30 days) - single GROUP BY query
    period_start = (now - timedelta(days=29)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    result = await session.execute(
        select(
            sa_func.date(Task.closed_at).label("day"),
            sa_func.count(Task.id).label("cnt"),
        )
        .where(
            Task.status.in_(["done", "closed"]),
            Task.closed_at >= period_start,
        )
        .group_by(sa_func.date(Task.closed_at))
    )
    day_counts = {str(row.day): row.cnt for row in result.all()}

    throughput_trend = []
    for i in range(30):
        day_start = (now - timedelta(days=29 - i)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        day_str = day_start.strftime("%Y-%m-%d")
        throughput_trend.append({"date": day_str, "count": day_counts.get(day_str, 0)})

    return AnalyticsOverviewResponse(
        tasks_completed_week=tasks_completed_week,
        tasks_completed_month=tasks_completed_month,
        avg_time_to_resolve=avg_time_to_resolve,
        agent_workload=agent_workload,
        bottleneck_agent=bottleneck_agent,
        throughput_trend=throughput_trend,
    )


@router.get("/agents/{name}", response_model=AgentAnalyticsResponse)
async def agent_analytics(
    name: str,
    session: AsyncSession = Depends(get_session),
):
    """Аналитика по конкретному агенту."""
    # Find agent
    result = await session.execute(select(Agent).where(Agent.name == name))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Агент не найден")

    # Tasks completed
    result = await session.execute(
        select(sa_func.count(Task.id)).where(
            Task.executor_id == agent.id,
            Task.status.in_(["done", "closed"]),
        )
    )
    tasks_completed = result.scalar() or 0

    # Avg response time
    result = await session.execute(
        select(Task).where(
            Task.executor_id == agent.id,
            Task.status.in_(["done", "closed"]),
            Task.closed_at.isnot(None),
        )
    )
    completed_tasks = result.scalars().all()
    response_times = []
    for task in completed_tasks:
        created = task.created_at
        closed = task.closed_at
        if created and closed:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if closed.tzinfo is None:
                closed = closed.replace(tzinfo=timezone.utc)
            response_times.append((closed - created).total_seconds())

    avg_response_time = (
        sum(response_times) / len(response_times) if response_times else 0.0
    )

    # Delegation count
    result = await session.execute(
        select(sa_func.count(DelegationTrace.id)).where(
            DelegationTrace.source_agent == name
        )
    )
    delegation_count = result.scalar() or 0

    # Feedback score
    result = await session.execute(
        select(sa_func.avg(Feedback.rating)).where(
            Feedback.agent_name == name,
            Feedback.rating.isnot(None),
        )
    )
    feedback_score = result.scalar()

    # SLA compliance
    result = await session.execute(
        select(Task).where(
            Task.executor_id == agent.id,
            Task.sla_target_seconds.isnot(None),
            Task.status.in_(["done", "closed"]),
        )
    )
    sla_tasks = result.scalars().all()
    sla_met = 0
    for task in sla_tasks:
        created = task.created_at
        closed = task.closed_at
        if created and closed and task.sla_target_seconds:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if closed.tzinfo is None:
                closed = closed.replace(tzinfo=timezone.utc)
            elapsed = (closed - created).total_seconds()
            if elapsed <= task.sla_target_seconds:
                sla_met += 1

    sla_compliance_percent = (
        (sla_met / len(sla_tasks) * 100.0) if sla_tasks else 100.0
    )

    return AgentAnalyticsResponse(
        agent_name=name,
        tasks_completed=tasks_completed,
        avg_response_time=round(avg_response_time, 2),
        delegation_count=delegation_count,
        feedback_score=float(feedback_score) if feedback_score else None,
        sla_compliance_percent=round(sla_compliance_percent, 1),
    )


@router.get("/productivity", response_model=ProductivityResponse)
async def productivity_metrics(
    session: AsyncSession = Depends(get_session),
):
    """Метрики продуктивности команды."""
    now = datetime.now(timezone.utc)

    # Created vs completed per day (last 7 days) - two GROUP BY queries
    week_start = (now - timedelta(days=6)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    result = await session.execute(
        select(
            sa_func.date(Task.created_at).label("day"),
            sa_func.count(Task.id).label("cnt"),
        )
        .where(Task.created_at >= week_start)
        .group_by(sa_func.date(Task.created_at))
    )
    created_by_day = {str(row.day): row.cnt for row in result.all()}

    result = await session.execute(
        select(
            sa_func.date(Task.closed_at).label("day"),
            sa_func.count(Task.id).label("cnt"),
        )
        .where(
            Task.status.in_(["done", "closed"]),
            Task.closed_at >= week_start,
        )
        .group_by(sa_func.date(Task.closed_at))
    )
    completed_by_day = {str(row.day): row.cnt for row in result.all()}

    created_vs_completed = []
    for i in range(7):
        day_start = (now - timedelta(days=6 - i)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        day_str = day_start.strftime("%Y-%m-%d")
        created_vs_completed.append({
            "date": day_str,
            "created": created_by_day.get(day_str, 0),
            "completed": completed_by_day.get(day_str, 0),
        })

    # Peak hours (count tasks created per hour)
    result = await session.execute(select(Task.created_at))
    all_timestamps = result.scalars().all()
    hour_counts = [0] * 24
    for ts in all_timestamps:
        if ts:
            hour_counts[ts.hour] += 1
    peak_hours = [{"hour": h, "count": c} for h, c in enumerate(hour_counts)]

    # Most used templates (placeholder - return empty for now)
    most_used_templates: list = []

    return ProductivityResponse(
        created_vs_completed=created_vs_completed,
        peak_hours=peak_hours,
        most_used_templates=most_used_templates,
    )
