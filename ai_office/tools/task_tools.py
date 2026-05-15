"""Инструменты для управления задачами."""

from langchain_core.tools import tool


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
    # В реальной реализации здесь будет запись в БД
    return (
        f"Задача создана: '{description}', "
        f"приоритет: {priority}, "
        f"исполнитель: {executor_name or 'не назначен'}"
    )


@tool
def update_task_status(task_id: int, new_status: str) -> str:
    """Обновить статус задачи.

    Args:
        task_id: ID задачи
        new_status: Новый статус (open, in_progress, done)

    Returns:
        Подтверждение обновления
    """
    # В реальной реализации здесь будет обновление в БД
    return f"Статус задачи #{task_id} обновлён на: {new_status}"


@tool
def assign_task(task_id: int, agent_name: str) -> str:
    """Назначить задачу агенту.

    Args:
        task_id: ID задачи
        agent_name: Имя агента (alice или sam)

    Returns:
        Подтверждение назначения
    """
    # В реальной реализации здесь будет обновление в БД
    return f"Задача #{task_id} назначена агенту: {agent_name}"


@tool
def get_active_tasks() -> str:
    """Получить список активных задач.

    Returns:
        Список активных задач в текстовом формате
    """
    # В реальной реализации здесь будет запрос к БД
    return "Активные задачи: пока нет задач в системе."
