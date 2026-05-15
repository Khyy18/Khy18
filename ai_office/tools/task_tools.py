"""Инструменты для управления задачами."""

from langchain_core.tools import tool
from sqlalchemy import select

from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent, Task
from ai_office.tools.db_helper import run_async


async def _create_task_in_db(description: str, priority: str, executor_name: str) -> str:
    """Создать задачу в базе данных."""
    async with async_session() as session:
        executor_id = None
        if executor_name:
            result = await session.execute(
                select(Agent).where(Agent.name.ilike(executor_name))
            )
            agent = result.scalar_one_or_none()
            if agent:
                executor_id = agent.id

        task = Task(
            description=description,
            creator_type="agent",
            creator_id="orchestrator",
            executor_id=executor_id,
            status="open",
            priority=priority,
        )
        session.add(task)
        await session.flush()

        # Записываем в лог активности
        # Ищем Alice как агента по умолчанию для логирования
        result = await session.execute(
            select(Agent).where(Agent.name == "Alice")
        )
        log_agent = result.scalar_one_or_none()
        if log_agent:
            log = ActivityLog(
                agent_id=log_agent.id,
                action_type="task_created",
                action_description=f"Создана задача: {description}",
            )
            session.add(log)

        await session.commit()
        return (
            f"Задача создана (ID: {task.id}): '{description}', "
            f"приоритет: {priority}, "
            f"исполнитель: {executor_name or 'не назначен'}"
        )


async def _update_task_status_in_db(task_id: int, new_status: str) -> str:
    """Обновить статус задачи в базе данных."""
    async with async_session() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            return f"Задача #{task_id} не найдена."

        task.status = new_status
        await session.commit()
        return f"Статус задачи #{task_id} обновлён на: {new_status}"


async def _assign_task_in_db(task_id: int, agent_name: str) -> str:
    """Назначить задачу агенту в базе данных."""
    async with async_session() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            return f"Задача #{task_id} не найдена."

        result = await session.execute(
            select(Agent).where(Agent.name.ilike(agent_name))
        )
        agent = result.scalar_one_or_none()
        if not agent:
            return f"Агент '{agent_name}' не найден."

        task.executor_id = agent.id
        await session.commit()
        return f"Задача #{task_id} назначена агенту: {agent_name}"


async def _get_active_tasks_from_db() -> str:
    """Получить список активных задач из базы данных."""
    async with async_session() as session:
        result = await session.execute(
            select(Task).where(Task.status.in_(["open", "in_progress"]))
        )
        tasks = result.scalars().all()

        if not tasks:
            return "Активные задачи: пока нет задач в системе."

        lines = ["Активные задачи:"]
        for t in tasks:
            lines.append(f"  #{t.id} [{t.status}] {t.priority}: {t.description}")
        return "\n".join(lines)


@tool
def create_task(description: str, priority: str = "medium", executor_name: str = "") -> str:
    """Создать новую задачу.

    Args:
        description: Описание задачи
        priority: Приоритет задачи (low, medium, high)
        executor_name: Имя исполнителя (alice или sam), пустая строка если не назначен

    Returns:
        Подтверждение создания задачи
    """
    return run_async(_create_task_in_db(description, priority, executor_name))


@tool
def update_task_status(task_id: int, new_status: str) -> str:
    """Обновить статус задачи.

    Args:
        task_id: ID задачи
        new_status: Новый статус (open, in_progress, done)

    Returns:
        Подтверждение обновления
    """
    return run_async(_update_task_status_in_db(task_id, new_status))


@tool
def assign_task(task_id: int, agent_name: str) -> str:
    """Назначить задачу агенту.

    Args:
        task_id: ID задачи
        agent_name: Имя агента (alice или sam)

    Returns:
        Подтверждение назначения
    """
    return run_async(_assign_task_in_db(task_id, agent_name))


@tool
def get_active_tasks() -> str:
    """Получить список активных задач.

    Returns:
        Список активных задач в текстовом формате
    """
    return run_async(_get_active_tasks_from_db())
