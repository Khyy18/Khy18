"""Инструменты QA инженера - записывают активность в БД."""

from langchain_core.tools import tool
from sqlalchemy import select

from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени Leo."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "Leo")
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
async def create_test_plan(feature: str, scenarios: str) -> str:
    """Создать тест-план для фичи (имитация с логированием в БД).

    Args:
        feature: Название фичи для тестирования
        scenarios: Описание сценариев для покрытия

    Returns:
        Структурированный тест-план
    """
    result = (
        f"[Имитация] Тест-план для: '{feature}'\n"
        f"Сценарии: {scenarios}\n"
        f"Тест-кейсы:\n"
        f"1. Позитивный: основной флоу работает корректно\n"
        f"2. Негативный: обработка невалидных данных\n"
        f"3. Граничный: предельные значения\n"
        f"4. Регрессионный: существующий функционал не нарушен"
    )
    await _log_activity("test_plan_created", f"Тест-план: {feature}")
    return result


@tool
async def report_bug(title: str, steps: str, expected: str, actual: str) -> str:
    """Зарегистрировать баг-репорт (имитация с логированием в БД).

    Args:
        title: Заголовок бага
        steps: Шаги воспроизведения
        expected: Ожидаемое поведение
        actual: Фактическое поведение

    Returns:
        Подтверждение регистрации бага
    """
    result = (
        f"[Имитация] Баг зарегистрирован: '{title}'\n"
        f"Шаги: {steps}\n"
        f"Ожидание: {expected}\n"
        f"Реальность: {actual}\n"
        f"Приоритет: major\n"
        f"Статус: open"
    )
    await _log_activity("bug_reported", f"Баг: {title}")
    return result


@tool
async def verify_fix(bug_id: str, verification_steps: str) -> str:
    """Верифицировать исправление бага (имитация с логированием в БД).

    Args:
        bug_id: Идентификатор бага
        verification_steps: Шаги верификации

    Returns:
        Результат верификации
    """
    result = (
        f"[Имитация] Верификация бага #{bug_id}:\n"
        f"Шаги проверки: {verification_steps}\n"
        f"Результат: исправление подтверждено\n"
        f"Статус: verified"
    )
    await _log_activity("fix_verified", f"Верификация бага #{bug_id}")
    return result
