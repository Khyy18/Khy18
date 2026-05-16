"""Proactive scheduled tasks for AI Office agents.

Alice: daily standup summary
Eva: weekly analytics report
Leo: overdue task alerts
Nova: hourly health check
"""

import logging
from datetime import datetime, timezone, timedelta

import psutil
from sqlalchemy import select, func

from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent, Task
from ai_office.telegram.sender import send_to_chat

logger = logging.getLogger(__name__)


async def alice_daily_standup() -> None:
    """Alice: ежедневный стендап - сводка по открытым и просроченным задачам."""
    async with async_session() as session:
        # Get Alice agent
        result = await session.execute(
            select(Agent).where(Agent.name == "Alice")
        )
        alice = result.scalar_one_or_none()

        # Get open tasks
        result = await session.execute(
            select(Task).where(Task.status.in_(["open", "in_progress"]))
        )
        open_tasks = result.scalars().all()

        # Get overdue tasks (open > 24h)
        threshold = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await session.execute(
            select(Task).where(
                Task.status.in_(["open", "in_progress"]),
                Task.created_at < threshold,
            )
        )
        overdue_tasks = result.scalars().all()

        # Format standup message
        lines = [
            "📋 Ежедневный стендап от Alice",
            f"Дата: {datetime.now(timezone.utc).strftime('%d.%m.%Y')}",
            "",
            f"Открытых задач: {len(open_tasks)}",
            f"Просроченных (>24ч): {len(overdue_tasks)}",
        ]

        if open_tasks:
            lines.append("")
            lines.append("Текущие задачи:")
            for task in open_tasks[:10]:
                status_icon = "🔵" if task.status == "open" else "🟡"
                lines.append(f"  {status_icon} #{task.id}: {task.description}")

        if overdue_tasks:
            lines.append("")
            lines.append("⚠️ Просроченные:")
            for task in overdue_tasks[:5]:
                lines.append(f"  🔴 #{task.id}: {task.description}")

        message = "\n".join(lines)

        # Send to Telegram
        await send_to_chat(message)

        # Log activity
        if alice:
            log = ActivityLog(
                agent_id=alice.id,
                action_type="proactive_standup",
                action_description=f"Стендап: {len(open_tasks)} открытых, {len(overdue_tasks)} просроченных",
            )
            session.add(log)
            await session.commit()

    logger.info("Alice daily standup completed")


async def eva_weekly_report() -> None:
    """Eva: еженедельный аналитический отчёт."""
    async with async_session() as session:
        # Get Eva agent
        result = await session.execute(
            select(Agent).where(Agent.name == "Eva")
        )
        eva = result.scalar_one_or_none()

        # Tasks completed this week
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        result = await session.execute(
            select(Task).where(
                Task.status == "done",
                Task.closed_at >= week_ago,
            )
        )
        completed_tasks = result.scalars().all()

        # Total open tasks
        result = await session.execute(
            select(func.count(Task.id)).where(
                Task.status.in_(["open", "in_progress"])
            )
        )
        open_count = result.scalar() or 0

        # Calculate average time-to-close
        close_times = []
        for task in completed_tasks:
            if task.closed_at and task.created_at:
                closed = task.closed_at
                created = task.created_at
                # Normalize timezone awareness
                if closed.tzinfo is None:
                    closed = closed.replace(tzinfo=timezone.utc)
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                delta = closed - created
                close_times.append(delta.total_seconds() / 3600)

        avg_close_hours = (
            sum(close_times) / len(close_times) if close_times else 0
        )

        # Agent workload (tasks in progress per agent)
        result = await session.execute(
            select(Agent.name, func.count(Task.id))
            .join(Task, Task.executor_id == Agent.id, isouter=True)
            .where(Task.status.in_(["open", "in_progress"]))
            .group_by(Agent.name)
        )
        workload = result.all()

        # Format report
        lines = [
            "📊 Еженедельный отчёт от Eva",
            f"Период: {week_ago.strftime('%d.%m')} - {datetime.now(timezone.utc).strftime('%d.%m.%Y')}",
            "",
            f"Завершено задач: {len(completed_tasks)}",
            f"Среднее время закрытия: {avg_close_hours:.1f} ч",
            f"Открытых задач: {open_count}",
        ]

        if workload:
            lines.append("")
            lines.append("Нагрузка по агентам:")
            for agent_name, count in workload:
                lines.append(f"  {agent_name}: {count} задач")

        message = "\n".join(lines)

        # Send to Telegram
        await send_to_chat(message)

        # Log activity
        if eva:
            log = ActivityLog(
                agent_id=eva.id,
                action_type="proactive_report",
                action_description=f"Недельный отчёт: {len(completed_tasks)} завершено, среднее закрытие {avg_close_hours:.1f}ч",
            )
            session.add(log)
            await session.commit()

    logger.info("Eva weekly report completed")


async def leo_overdue_alert() -> None:
    """Leo: алерт о просроченных задачах (открыты > 24ч)."""
    async with async_session() as session:
        # Get Leo agent
        result = await session.execute(
            select(Agent).where(Agent.name == "Leo")
        )
        leo = result.scalar_one_or_none()

        # Find overdue tasks (open > 24h)
        threshold = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await session.execute(
            select(Task).where(
                Task.status.in_(["open", "in_progress"]),
                Task.created_at < threshold,
            )
        )
        overdue_tasks = result.scalars().all()

        if not overdue_tasks:
            logger.info("Leo: no overdue tasks found")
            # Still log the check
            if leo:
                log = ActivityLog(
                    agent_id=leo.id,
                    action_type="proactive_overdue_alert",
                    action_description="Проверка: просроченных задач нет",
                )
                session.add(log)
                await session.commit()
            return

        # Format alert
        lines = [
            f"⚠️ Алерт от Leo: {len(overdue_tasks)} просроченных задач",
            "",
        ]
        for task in overdue_tasks[:10]:
            created = task.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_hours = (
                datetime.now(timezone.utc) - created
            ).total_seconds() / 3600
            lines.append(
                f"  🔴 #{task.id}: {task.description} ({age_hours:.0f}ч)"
            )

        message = "\n".join(lines)

        # Send to Telegram
        await send_to_chat(message)

        # Log activity
        if leo:
            log = ActivityLog(
                agent_id=leo.id,
                action_type="proactive_overdue_alert",
                action_description=f"Алерт: {len(overdue_tasks)} просроченных задач",
            )
            session.add(log)
            await session.commit()

    logger.info("Leo overdue alert completed")


async def nova_health_check() -> None:
    """Nova: проверка здоровья системы (DB, память, CPU).

    Sends to Telegram ONLY if something is wrong.
    """
    issues = []

    # Check DB connectivity
    try:
        async with async_session() as session:
            await session.execute(select(func.count(Agent.id)))
    except Exception as e:
        issues.append(f"DB: {str(e)}")

    # Check memory usage
    try:
        memory = psutil.virtual_memory()
        if memory.percent > 90:
            issues.append(f"RAM: {memory.percent}% использовано")
    except Exception as e:
        issues.append(f"RAM check failed: {str(e)}")

    # Check CPU usage
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > 90:
            issues.append(f"CPU: {cpu_percent}% загрузка")
    except Exception as e:
        issues.append(f"CPU check failed: {str(e)}")

    # Log activity
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "Nova")
        )
        nova = result.scalar_one_or_none()

        if nova:
            status_text = (
                f"Проблемы: {', '.join(issues)}" if issues else "Все системы в норме"
            )
            log = ActivityLog(
                agent_id=nova.id,
                action_type="proactive_health_check",
                action_description=status_text,
            )
            session.add(log)
            await session.commit()

    # Send to Telegram only if there are issues
    if issues:
        lines = [
            "🚨 Health Check от Nova: обнаружены проблемы",
            "",
        ]
        for issue in issues:
            lines.append(f"  ❌ {issue}")
        message = "\n".join(lines)
        await send_to_chat(message)
    else:
        logger.info("Nova health check: all systems OK")
