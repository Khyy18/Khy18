"""Инструменты бизнес-аналитика - записывают активность в БД."""

from langchain_core.tools import tool
from sqlalchemy import select

from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени Eva."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "Eva")
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
async def create_user_story(feature: str, persona: str) -> str:
    """Создать user story в стандартном формате (имитация с логированием в БД).

    Args:
        feature: Описание фичи
        persona: Целевая персона/роль пользователя

    Returns:
        Сформулированная user story
    """
    result = (
        f"[Имитация] User Story:\n"
        f"Как {persona}, я хочу {feature}, "
        f"чтобы повысить эффективность работы.\n"
        f"Acceptance Criteria:\n"
        f"- Функциональность доступна из основного интерфейса\n"
        f"- Время отклика не превышает 2 секунд\n"
        f"- Поддержка мобильных устройств"
    )
    await _log_activity("user_story_created", f"User story: {feature} (персона: {persona})")
    return result


@tool
async def analyze_requirements(text: str) -> str:
    """Проанализировать требования и выявить пробелы (имитация с логированием в БД).

    Args:
        text: Текст требований для анализа

    Returns:
        Результат анализа требований
    """
    result = (
        f"[Имитация] Анализ требований:\n"
        f"Исходный текст: '{text}'\n"
        f"Выявленные пробелы:\n"
        f"1. Не указаны нефункциональные требования\n"
        f"2. Необходимо уточнить граничные условия\n"
        f"3. Отсутствуют критерии приёмки"
    )
    await _log_activity("requirements_analyzed", f"Анализ требований: {text[:50]}")
    return result


@tool
async def generate_report(topic: str, data_points: str) -> str:
    """Сгенерировать аналитический отчёт (имитация с логированием в БД).

    Args:
        topic: Тема отчёта
        data_points: Ключевые данные для включения в отчёт

    Returns:
        Аналитический отчёт
    """
    result = (
        f"[Имитация] Аналитический отчёт: {topic}\n"
        f"Данные: {data_points}\n"
        f"Выводы:\n"
        f"1. Показатели в пределах нормы\n"
        f"2. Рекомендуется фокус на ключевых метриках\n"
        f"3. Необходим следующий замер через 1 неделю"
    )
    await _log_activity("report_generated", f"Отчёт: {topic}")
    return result
