"""Система обнаружения оттока и win-back сообщений."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.models import (
    ActivityLog,
    Agent,
    Task,
    WinbackLog,
    Workspace,
)


@dataclass
class EngagementScore:
    """Оценка вовлечённости рабочего пространства."""

    messages_per_day: float
    tasks_created: int
    tasks_completed: int
    agents_used: int
    score: float


async def calculate_engagement(
    workspace_id: int, session: AsyncSession
) -> EngagementScore:
    """Рассчитывает оценку вовлечённости workspace за последние 7 дней.

    Формула: messages_per_day * 10 + tasks_completed * 5 + agents_used * 3

    Args:
        workspace_id: ID рабочего пространства
        session: Асинхронная сессия БД

    Returns:
        EngagementScore с детализацией метрик
    """
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # Activity count (messages per day)
    activity_result = await session.execute(
        select(func.count(ActivityLog.id)).where(
            ActivityLog.workspace_id == workspace_id,
            ActivityLog.timestamp >= week_ago,
        )
    )
    total_activities = activity_result.scalar() or 0
    messages_per_day = total_activities / 7.0

    # Tasks created
    tasks_created_result = await session.execute(
        select(func.count(Task.id)).where(
            Task.workspace_id == workspace_id,
            Task.created_at >= week_ago,
        )
    )
    tasks_created = tasks_created_result.scalar() or 0

    # Tasks completed
    tasks_completed_result = await session.execute(
        select(func.count(Task.id)).where(
            Task.workspace_id == workspace_id,
            Task.status == "completed",
            Task.closed_at >= week_ago,
        )
    )
    tasks_completed = tasks_completed_result.scalar() or 0

    # Agents used (distinct agents with activity)
    agents_result = await session.execute(
        select(func.count(func.distinct(ActivityLog.agent_id))).where(
            ActivityLog.workspace_id == workspace_id,
            ActivityLog.timestamp >= week_ago,
        )
    )
    agents_used = agents_result.scalar() or 0

    score = messages_per_day * 10 + tasks_completed * 5 + agents_used * 3

    return EngagementScore(
        messages_per_day=round(messages_per_day, 2),
        tasks_created=tasks_created,
        tasks_completed=tasks_completed,
        agents_used=agents_used,
        score=round(score, 2),
    )


async def detect_churning_workspaces(session: AsyncSession) -> list[dict]:
    """Находит рабочие пространства, неактивные 3+ дней.

    Returns:
        Список словарей с workspace_id, days_inactive, last_activity, recommended_action
    """
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=3)

    # Get all workspaces
    ws_result = await session.execute(select(Workspace))
    workspaces = ws_result.scalars().all()

    at_risk = []
    for ws in workspaces:
        # Find last activity
        last_activity_result = await session.execute(
            select(func.max(ActivityLog.timestamp)).where(
                ActivityLog.workspace_id == ws.id
            )
        )
        last_activity = last_activity_result.scalar()

        if last_activity is None:
            # No activity ever - use created_at
            last_activity = ws.created_at

        # Make timezone-aware for comparison if needed
        if last_activity and last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)

        if last_activity and last_activity < threshold:
            days_inactive = (now - last_activity).days

            # Determine recommended action based on inactivity duration
            if days_inactive >= 14:
                recommended_action = "discount"
            elif days_inactive >= 7:
                recommended_action = "update"
            else:
                recommended_action = "nudge"

            at_risk.append({
                "workspace_id": ws.id,
                "workspace_name": ws.name,
                "days_inactive": days_inactive,
                "last_activity": last_activity,
                "recommended_action": recommended_action,
            })

    return at_risk


async def record_winback(
    workspace_id: int, level: str, session: AsyncSession
) -> None:
    """Записывает отправку win-back сообщения.

    Args:
        workspace_id: ID рабочего пространства
        level: Уровень - 'nudge', 'update', или 'discount'
        session: Асинхронная сессия БД
    """
    log_entry = WinbackLog(workspace_id=workspace_id, level=level)
    session.add(log_entry)
    await session.commit()


async def can_send_winback(
    workspace_id: int, level: str, session: AsyncSession
) -> bool:
    """Проверяет, можно ли отправить win-back сообщение.

    Ограничения: макс. 1 за период (7 дней для nudge, 14 для update, 30 для discount).

    Args:
        workspace_id: ID рабочего пространства
        level: Уровень сообщения
        session: Асинхронная сессия БД

    Returns:
        True если можно отправить, False если лимит не истёк
    """
    periods = {
        "nudge": 7,
        "update": 14,
        "discount": 30,
    }
    period_days = periods.get(level, 7)
    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)

    result = await session.execute(
        select(func.count(WinbackLog.id)).where(
            WinbackLog.workspace_id == workspace_id,
            WinbackLog.level == level,
            WinbackLog.sent_at >= cutoff,
        )
    )
    count = result.scalar() or 0
    return count == 0
