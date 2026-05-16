"""Интеграция с Linear - управление задачами через GraphQL API."""

import logging
from typing import Any, Optional

import httpx

from ai_office.core.config import settings

logger = logging.getLogger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"


def _get_headers() -> dict[str, str]:
    """Получить заголовки для запроса к Linear API."""
    return {
        "Authorization": settings.linear_api_key,
        "Content-Type": "application/json",
    }


async def create_linear_issue(
    title: str,
    description: str = "",
    team_id: str = "",
    priority: int = 0,
) -> dict[str, Any]:
    """Создать задачу в Linear.

    Args:
        title: Название задачи
        description: Описание задачи
        team_id: ID команды в Linear
        priority: Приоритет (0-4, где 0 - без приоритета)

    Returns:
        Данные созданной задачи
    """
    if not settings.linear_api_key:
        return {"error": "LINEAR_API_KEY не настроен"}

    mutation = """
    mutation CreateIssue($title: String!, $description: String, $teamId: String!, $priority: Int) {
        issueCreate(input: {
            title: $title
            description: $description
            teamId: $teamId
            priority: $priority
        }) {
            success
            issue {
                id
                identifier
                title
                url
            }
        }
    }
    """

    variables = {
        "title": title,
        "description": description,
        "teamId": team_id,
        "priority": priority,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                LINEAR_API_URL,
                json={"query": mutation, "variables": variables},
                headers=_get_headers(),
                timeout=15.0,
            )

        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}"}

        data = response.json()
        if "errors" in data:
            return {"error": data["errors"][0].get("message", "Unknown error")}

        issue_data = data.get("data", {}).get("issueCreate", {})
        return issue_data.get("issue", {})

    except Exception as e:
        logger.error("Ошибка создания задачи в Linear: %s", str(e))
        return {"error": str(e)}


async def list_linear_issues(
    team_id: str = "",
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Получить список задач из Linear.

    Args:
        team_id: ID команды для фильтрации
        status: Статус для фильтрации (опционально)

    Returns:
        Список задач
    """
    if not settings.linear_api_key:
        return []

    filter_parts = []
    if team_id:
        filter_parts.append(f'team: {{ id: {{ eq: "{team_id}" }} }}')
    if status:
        filter_parts.append(f'state: {{ name: {{ eq: "{status}" }} }}')

    filter_str = ", ".join(filter_parts)
    filter_arg = f"(filter: {{ {filter_str} }})" if filter_str else ""

    query = f"""
    query {{
        issues{filter_arg} {{
            nodes {{
                id
                identifier
                title
                state {{
                    name
                }}
                priority
                url
            }}
        }}
    }}
    """

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                LINEAR_API_URL,
                json={"query": query},
                headers=_get_headers(),
                timeout=15.0,
            )

        if response.status_code != 200:
            return []

        data = response.json()
        if "errors" in data:
            logger.error("Linear API error: %s", data["errors"])
            return []

        return data.get("data", {}).get("issues", {}).get("nodes", [])

    except Exception as e:
        logger.error("Ошибка получения задач из Linear: %s", str(e))
        return []


async def update_linear_issue(
    issue_id: str,
    status: Optional[str] = None,
) -> dict[str, Any]:
    """Обновить задачу в Linear.

    Args:
        issue_id: ID задачи
        status: Новый статус (имя состояния)

    Returns:
        Данные обновленной задачи
    """
    if not settings.linear_api_key:
        return {"error": "LINEAR_API_KEY не настроен"}

    # Если нужно обновить статус, сначала найти stateId
    input_fields = []
    if status:
        # Linear требует stateId, не имя
        input_fields.append(f'stateId: "{status}"')

    if not input_fields:
        return {"error": "Нет полей для обновления"}

    input_str = ", ".join(input_fields)

    mutation = f"""
    mutation {{
        issueUpdate(id: "{issue_id}", input: {{ {input_str} }}) {{
            success
            issue {{
                id
                identifier
                title
                state {{
                    name
                }}
                url
            }}
        }}
    }}
    """

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                LINEAR_API_URL,
                json={"query": mutation},
                headers=_get_headers(),
                timeout=15.0,
            )

        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}"}

        data = response.json()
        if "errors" in data:
            return {"error": data["errors"][0].get("message", "Unknown error")}

        issue_data = data.get("data", {}).get("issueUpdate", {})
        return issue_data.get("issue", {})

    except Exception as e:
        logger.error("Ошибка обновления задачи в Linear: %s", str(e))
        return {"error": str(e)}
