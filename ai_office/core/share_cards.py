"""Генерация карточек для шаринга результатов."""

from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.models import Task, Agent


async def generate_task_card(task_id: int, session: AsyncSession) -> dict:
    """Генерирует карточку задачи для шаринга.

    Args:
        task_id: ID задачи
        session: Асинхронная сессия БД

    Returns:
        Словарь с данными карточки
    """
    result = await session.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if task is None:
        return {
            "task_description": "",
            "agent_name": "",
            "completed_in": "",
            "priority": "",
            "share_text": "Задача не найдена",
        }

    # Определяем имя агента
    agent_name = "AI Office"
    if task.executor_id:
        agent_result = await session.execute(
            select(Agent).where(Agent.id == task.executor_id)
        )
        agent = agent_result.scalar_one_or_none()
        if agent:
            agent_name = agent.name

    # Вычисляем время выполнения
    completed_in = "в работе"
    if task.closed_at and task.created_at:
        delta = task.closed_at - task.created_at
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        if hours > 0:
            completed_in = f"{hours}ч {minutes}мин"
        else:
            completed_in = f"{minutes}мин"

    priority_map = {
        "high": "Высокий",
        "medium": "Средний",
        "low": "Низкий",
        "critical": "Критический",
    }
    priority_text = priority_map.get(task.priority, task.priority)

    share_text = (
        f"AI Office выполнил задачу!\n"
        f"Задача: {task.description[:100]}\n"
        f"Агент: {agent_name}\n"
        f"Приоритет: {priority_text}\n"
        f"Время: {completed_in}"
    )

    return {
        "task_description": task.description,
        "agent_name": agent_name,
        "completed_in": completed_in,
        "priority": priority_text,
        "share_text": share_text,
    }


async def generate_weekly_card(workspace_id: int, session: AsyncSession) -> dict:
    """Генерирует еженедельную сводку для шаринга.

    Args:
        workspace_id: ID рабочего пространства
        session: Асинхронная сессия БД

    Returns:
        Словарь с данными недельной сводки
    """
    week_ago = datetime.utcnow() - timedelta(days=7)

    # Количество выполненных задач за неделю
    tasks_query = select(func.count(Task.id)).where(
        Task.status == "done",
        Task.closed_at >= week_ago,
    )
    if workspace_id:
        tasks_query = tasks_query.where(Task.workspace_id == workspace_id)

    tasks_result = await session.execute(tasks_query)
    tasks_completed = tasks_result.scalar() or 0

    # Самый активный агент
    top_agent_query = (
        select(Agent.name, func.count(Task.id).label("task_count"))
        .join(Task, Task.executor_id == Agent.id)
        .where(Task.status == "done", Task.closed_at >= week_ago)
    )
    if workspace_id:
        top_agent_query = top_agent_query.where(Task.workspace_id == workspace_id)
    top_agent_query = top_agent_query.group_by(Agent.name).order_by(
        func.count(Task.id).desc()
    ).limit(1)

    top_agent_result = await session.execute(top_agent_query)
    top_agent_row = top_agent_result.first()
    top_agent = top_agent_row[0] if top_agent_row else "N/A"

    # Оценка сэкономленного времени (30 мин на задачу)
    total_minutes_saved = tasks_completed * 30
    hours_saved = total_minutes_saved // 60
    mins_saved = total_minutes_saved % 60
    total_time_saved = f"{hours_saved}ч {mins_saved}мин"

    share_text = (
        f"Итоги недели в AI Office!\n"
        f"Выполнено задач: {tasks_completed}\n"
        f"Лучший агент: {top_agent}\n"
        f"Сэкономлено времени: {total_time_saved}"
    )

    return {
        "tasks_completed": tasks_completed,
        "top_agent": top_agent,
        "total_time_saved": total_time_saved,
        "share_text": share_text,
    }
