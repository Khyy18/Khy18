"""Интеграция с Notion - работа с базами данных и страницами."""

import logging
from typing import Any, Optional

import httpx

from ai_office.core.config import settings

logger = logging.getLogger(__name__)

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _get_headers() -> dict[str, str]:
    """Получить заголовки для запроса к Notion API."""
    return {
        "Authorization": f"Bearer {settings.notion_api_key}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


async def create_notion_page(
    database_id: str,
    title: str,
    content: str = "",
) -> dict[str, Any]:
    """Создать страницу в базе данных Notion.

    Args:
        database_id: ID базы данных Notion
        title: Заголовок страницы
        content: Текстовое содержимое страницы

    Returns:
        Данные созданной страницы
    """
    if not settings.notion_api_key:
        return {"error": "NOTION_API_KEY не настроен"}

    payload: dict[str, Any] = {
        "parent": {"database_id": database_id},
        "properties": {
            "Name": {
                "title": [{"text": {"content": title}}]
            }
        },
    }

    # Добавляем контент как блок параграфа
    if content:
        payload["children"] = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                },
            }
        ]

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{NOTION_API_URL}/pages",
                json=payload,
                headers=_get_headers(),
                timeout=15.0,
            )

        if response.status_code not in (200, 201):
            error_data = response.json() if response.content else {}
            return {"error": f"HTTP {response.status_code}: {error_data.get('message', '')}"}

        return response.json()

    except Exception as e:
        logger.error("Ошибка создания страницы в Notion: %s", str(e))
        return {"error": str(e)}


async def query_notion_database(
    database_id: str,
    filter_dict: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Запросить данные из базы данных Notion.

    Args:
        database_id: ID базы данных Notion
        filter_dict: Фильтр в формате Notion API (опционально)

    Returns:
        Список страниц из базы данных
    """
    if not settings.notion_api_key:
        return []

    payload: dict[str, Any] = {}
    if filter_dict:
        payload["filter"] = filter_dict

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{NOTION_API_URL}/databases/{database_id}/query",
                json=payload,
                headers=_get_headers(),
                timeout=15.0,
            )

        if response.status_code != 200:
            logger.error("Notion API error: HTTP %d", response.status_code)
            return []

        data = response.json()
        return data.get("results", [])

    except Exception as e:
        logger.error("Ошибка запроса к базе данных Notion: %s", str(e))
        return []
