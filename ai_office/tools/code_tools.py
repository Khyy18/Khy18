"""Инструменты разработчика - записывают активность в БД."""

from langchain_core.tools import tool
from sqlalchemy import select

from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени Sam."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "Sam")
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
async def execute_code(code: str, language: str = "python") -> str:
    """Выполнить фрагмент кода (имитация с логированием в БД).

    Args:
        code: Код для выполнения
        language: Язык программирования (python, javascript и т.д.)

    Returns:
        Результат выполнения
    """
    result = f"[Имитация] Код на {language} выполнен успешно. Результат: OK"
    await _log_activity("code_executed", f"Выполнен код на {language}")
    return result


@tool
async def review_code(code: str, context: str = "") -> str:
    """Провести ревью кода (имитация с логированием в БД).

    Args:
        code: Код для ревью
        context: Контекст задачи

    Returns:
        Результат ревью
    """
    result = (
        "[Имитация] Код проверен. "
        "Замечаний нет, качество соответствует стандартам."
    )
    await _log_activity("code_reviewed", f"Проведено ревью кода. Контекст: {context or 'общий'}")
    return result


@tool
async def search_docs(query: str, source: str = "general") -> str:
    """Поиск в документации (имитация с логированием в БД).

    Args:
        query: Поисковый запрос
        source: Источник документации

    Returns:
        Найденная информация
    """
    result = f"[Имитация] Результаты поиска по запросу '{query}': информация найдена в {source}."
    await _log_activity("docs_searched", f"Поиск в документации: '{query}' (источник: {source})")
    return result
