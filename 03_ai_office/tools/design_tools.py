"""Инструменты UI/UX дизайнера - записывают активность в БД."""

from langchain_core.tools import tool
from sqlalchemy import select

from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени Max."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "Max")
        )
        agent = result.scalar_one_or_none()
        if agent:
            log = ActivityLog(
                agent_id=agent.id,
                action_type=action_type,
                action_description=description,
            )
            session.add(log)
            await session.commit()


@tool
async def review_design(description: str) -> str:
    """Провести ревью UI-решения (имитация с логированием в БД).

    Args:
        description: Описание дизайн-решения для ревью

    Returns:
        Результат ревью дизайна
    """
    result = (
        f"[Имитация] Ревью дизайна проведено для: '{description}'. "
        "Рекомендации: соблюдать консистентность UI-компонентов, "
        "обеспечить достаточный контраст и читаемость."
    )
    await _log_activity("design_reviewed", f"Ревью дизайна: {description}")
    return result


@tool
async def generate_wireframe(screen_name: str, requirements: str) -> str:
    """Сгенерировать описание вайрфрейма экрана (имитация с логированием в БД).

    Args:
        screen_name: Название экрана
        requirements: Требования к экрану

    Returns:
        Структура вайрфрейма
    """
    result = (
        f"[Имитация] Вайрфрейм для экрана '{screen_name}':\n"
        f"Требования: {requirements}\n"
        "Структура: Header -> Navigation -> Main Content -> Footer\n"
        "Компоненты: карточки, кнопки действий, панель статуса."
    )
    await _log_activity("wireframe_created", f"Создан вайрфрейм: {screen_name}")
    return result


@tool
async def suggest_ux_improvements(current_flow: str) -> str:
    """Предложить улучшения UX для текущего флоу (имитация с логированием в БД).

    Args:
        current_flow: Описание текущего пользовательского флоу

    Returns:
        Рекомендации по улучшению UX
    """
    result = (
        f"[Имитация] UX-аудит для флоу: '{current_flow}'.\n"
        "Рекомендации:\n"
        "1. Сократить количество шагов до цели\n"
        "2. Добавить визуальную обратную связь\n"
        "3. Обеспечить возможность отмены действий"
    )
    await _log_activity("ux_audit", f"UX-аудит: {current_flow}")
    return result
