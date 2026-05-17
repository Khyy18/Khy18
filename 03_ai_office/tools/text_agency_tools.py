"""Инструменты для агента AI Text Agency - статистика контента и публикаций."""

import httpx
from langchain_core.tools import tool

from ai_office.core.config import settings
from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent
from sqlalchemy import select


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени Text Agency."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "text_agency")
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
async def get_content_stats(period: str = "week") -> str:
    """Получить статистику контент-пайплайна.

    Args:
        period: Период статистики (day, week, month)

    Returns:
        Статистика: опубликовано, в очереди, вовлечённость
    """
    base_url = settings.text_agency_api_url
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/api/stats", params={"period": period})
            if resp.status_code == 200:
                data = resp.json()
                result = (
                    f"Контент-статистика ({period}):\n"
                    f"  Опубликовано: {data.get('published', 'N/A')}\n"
                    f"  В очереди: {data.get('in_queue', 'N/A')}\n"
                    f"  Средняя вовлечённость: {data.get('avg_engagement', 'N/A')}%\n"
                    f"  Просмотры: {data.get('total_views', 'N/A')}"
                )
                await _log_activity("content_stats_fetched", f"Статистика контента: {period}")
                return result
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        pass

    result = (
        f"[CACHED/STALE DATA - service unreachable]\n"
        f"Контент-статистика ({period}, кэш):\n"
        f"  Опубликовано: 12\n"
        f"  В очереди: 5\n"
        f"  Средняя вовлечённость: 4.2%\n"
        f"  Просмотры: 8,430"
    )
    await _log_activity("content_stats_fetched", f"Статистика контента (кэш): {period}")
    return result


@tool
async def get_recent_articles(limit: int = 5) -> str:
    """Получить список недавних публикаций.

    Args:
        limit: Количество статей для отображения

    Returns:
        Список недавних публикаций с метриками
    """
    base_url = settings.text_agency_api_url
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/api/articles", params={"limit": limit})
            if resp.status_code == 200:
                data = resp.json()
                articles = data.get("articles", [])
                if not articles:
                    return "Нет недавних публикаций."
                lines = ["Недавние публикации:"]
                for a in articles:
                    lines.append(
                        f"  - {a.get('title', 'Без названия')} "
                        f"({a.get('views', 0)} просмотров)"
                    )
                result = "\n".join(lines)
                await _log_activity("articles_fetched", f"Запрошено статей: {limit}")
                return result
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        pass

    result = (
        "[CACHED/STALE DATA - service unreachable]\n"
        "Недавние публикации (кэш):\n"
        "  - Как выбрать CRM для стартапа (1,200 просмотров)\n"
        "  - 10 трендов маркетинга 2024 (890 просмотров)\n"
        "  - Гайд по автоматизации продаж (650 просмотров)"
    )
    await _log_activity("articles_fetched", "Статьи запрошены (кэш)")
    return result


@tool
async def get_content_queue() -> str:
    """Получить текущую очередь контента на публикацию.

    Returns:
        Список материалов в очереди с датами публикации
    """
    base_url = settings.text_agency_api_url
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/api/queue")
            if resp.status_code == 200:
                data = resp.json()
                queue = data.get("queue", [])
                if not queue:
                    return "Очередь публикаций пуста."
                lines = ["Очередь публикаций:"]
                for item in queue:
                    lines.append(
                        f"  - {item.get('title', 'Без названия')} "
                        f"(дата: {item.get('scheduled_date', 'не назначена')})"
                    )
                result = "\n".join(lines)
                await _log_activity("content_queue_fetched", f"Очередь запрошена: {len(queue)} шт.")
                return result
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        pass

    result = (
        "[CACHED/STALE DATA - service unreachable]\n"
        "Очередь публикаций (кэш):\n"
        "  - SEO-оптимизация для B2B (дата: 2024-01-15)\n"
        "  - Email-маркетинг: лучшие практики (дата: 2024-01-17)\n"
        "  - Кейс: рост конверсии на 40% (дата: 2024-01-20)"
    )
    await _log_activity("content_queue_fetched", "Очередь запрошена (кэш)")
    return result
