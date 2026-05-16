"""Инструменты поиска информации - записывают активность в БД."""

import httpx
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
async def web_search(query: str, num_results: int = 5) -> str:
    """Поиск информации в интернете через DuckDuckGo.

    Args:
        query: Поисковый запрос
        num_results: Максимальное количество результатов (по умолчанию 5)

    Returns:
        Найденная информация в текстовом формате
    """
    url = "https://api.duckduckgo.com/"
    params = {"q": query, "format": "json", "no_html": "1"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)

        if response.status_code != 200:
            return f"Ошибка поиска: HTTP {response.status_code}"

        data = response.json()
        results = []

        # Абстрактный текст (основной ответ)
        if data.get("AbstractText"):
            results.append(f"Ответ: {data['AbstractText']}")

        # Основные результаты
        for item in data.get("Results", [])[:num_results]:
            if item.get("Text"):
                results.append(f"- {item['Text']}")

        # Связанные темы
        for topic in data.get("RelatedTopics", [])[:num_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"- {topic['Text']}")

        if not results:
            return f"По запросу '{query}' ничего не найдено. Попробуйте уточнить запрос."

        # Ограничиваем количество результатов
        output = "\n".join(results[:num_results])
        await _log_activity("web_search", f"Поиск: '{query}' ({len(results)} результатов)")
        return f"Результаты поиска по запросу '{query}':\n{output}"

    except httpx.TimeoutException:
        return f"Превышено время ожидания при поиске '{query}'."
    except Exception as e:
        return f"Ошибка поиска: {str(e)}"
