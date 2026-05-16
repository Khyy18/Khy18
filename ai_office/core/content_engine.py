"""Контент-движок для автоматического постинга Iris в Telegram-канал."""

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.models import ActivityLog, Agent, Task

# Schedule constants
WEEKLY_DIGEST_DAY = "monday"
WEEKLY_DIGEST_HOUR = 11
TIPS_DAYS = ["tuesday", "thursday"]
TIPS_HOUR = 14
CASE_STUDY_DAY = "friday"
CASE_STUDY_HOUR = 16

# Predefined tips in Russian
_TIPS = [
    "\U0001f4a1 Совет дня: Используйте @Sam для генерации кода - просто опишите задачу на русском языке!",
    "\U0001f4a1 Совет дня: Команда /tasks покажет все активные задачи вашей команды.",
    "\U0001f4a1 Совет дня: Eva может провести анализ рынка - просто попросите её об этом.",
    "\U0001f4a1 Совет дня: Max создаёт UI/UX прототипы за минуты. Попробуйте: '@Max сделай макет лендинга'.",
    "\U0001f4a1 Совет дня: Leo проверит качество кода и найдёт баги ещё до деплоя.",
    "\U0001f4a1 Совет дня: Nova автоматизирует DevOps задачи - CI/CD, мониторинг, деплой.",
    "\U0001f4a1 Совет дня: Oscar поможет с финансовым планированием и расчётом unit-экономики.",
    "\U0001f4a1 Совет дня: Iris создаёт маркетинговый контент - от постов до email-рассылок.",
    "\U0001f4a1 Совет дня: Делегируйте рутину агентам, сосредоточьтесь на стратегии!",
    "\U0001f4a1 Совет дня: Используйте шаблоны задач для ускорения типовых запросов.",
    "\U0001f4a1 Совет дня: Alice помнит контекст разговора - не нужно повторять детали.",
    "\U0001f4a1 Совет дня: Голосовые сообщения автоматически транскрибируются и обрабатываются.",
]


async def generate_weekly_post(workspace_id: int, session: AsyncSession) -> str:
    """Генерирует еженедельный дайджест для Telegram-канала.

    Собирает метрики: завершённые задачи, самый активный агент, экономия времени.

    Args:
        workspace_id: ID рабочего пространства
        session: Асинхронная сессия БД

    Returns:
        Текст поста на русском языке с эмодзи
    """
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # Tasks completed this week
    tasks_result = await session.execute(
        select(func.count(Task.id)).where(
            Task.workspace_id == workspace_id,
            Task.status == "completed",
            Task.closed_at >= week_ago,
        )
    )
    tasks_completed = tasks_result.scalar() or 0

    # Top agent by activity
    top_agent_result = await session.execute(
        select(Agent.name, func.count(ActivityLog.id).label("cnt"))
        .join(ActivityLog, Agent.id == ActivityLog.agent_id)
        .where(
            ActivityLog.workspace_id == workspace_id,
            ActivityLog.timestamp >= week_ago,
        )
        .group_by(Agent.name)
        .order_by(func.count(ActivityLog.id).desc())
        .limit(1)
    )
    top_agent_row = top_agent_result.first()
    top_agent = top_agent_row[0] if top_agent_row else "Alice"

    # Estimated time saved (5 min per task)
    time_saved = tasks_completed * 5

    post = (
        f"\U0001f4ca **Еженедельный дайджест AI Office**\n\n"
        f"\U00002705 Задач выполнено за неделю: **{tasks_completed}**\n"
        f"\U0001f3c6 Самый активный агент: **{top_agent}**\n"
        f"\U000023f0 Сэкономлено времени: ~**{time_saved} мин**\n\n"
        f"\U0001f680 Ваша команда AI-агентов работает 24/7!\n"
        f"Продолжайте делегировать задачи и фокусируйтесь на стратегии."
    )
    return post


async def generate_tip_post() -> str:
    """Возвращает случайный совет дня об использовании AI Office.

    Returns:
        Текст совета на русском языке
    """
    return random.choice(_TIPS)


async def generate_case_study(task_id: int, session: AsyncSession) -> str:
    """Генерирует кейс-стади по конкретной выполненной задаче.

    Args:
        task_id: ID задачи
        session: Асинхронная сессия БД

    Returns:
        Текст кейс-стади на русском языке
    """
    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        return "\U0000274c Задача не найдена."

    # Get executor agent name
    agent_name = "AI Office"
    if task.executor_id:
        agent_result = await session.execute(
            select(Agent.name).where(Agent.id == task.executor_id)
        )
        row = agent_result.scalar_one_or_none()
        if row:
            agent_name = row

    # Calculate time if possible
    duration_text = ""
    if task.closed_at and task.created_at:
        closed = task.closed_at
        created = task.created_at
        # Normalize timezone awareness
        if closed.tzinfo is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        elif closed.tzinfo is None and created.tzinfo is not None:
            closed = closed.replace(tzinfo=timezone.utc)
        duration = closed - created
        minutes = int(duration.total_seconds() / 60)
        if minutes < 60:
            duration_text = f"\U000023f1 Время выполнения: {minutes} мин"
        else:
            hours = minutes // 60
            duration_text = f"\U000023f1 Время выполнения: {hours} ч {minutes % 60} мин"

    post = (
        f"\U0001f4dd **Кейс: как AI Office решил задачу**\n\n"
        f"\U0001f4cc **Задача:** {task.description}\n"
        f"\U0001f916 **Исполнитель:** {agent_name}\n"
        f"\U0001f4ca **Приоритет:** {task.priority}\n"
    )
    if duration_text:
        post += f"{duration_text}\n"
    post += (
        f"\n\U00002705 Задача выполнена автоматически без участия человека.\n"
        f"AI Office берёт на себя рутину, чтобы вы могли сосредоточиться на главном."
    )
    return post
