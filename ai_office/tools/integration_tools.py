"""Инструменты интеграции с внешними сервисами (Linear, Notion)."""

from langchain_core.tools import tool

from ai_office.core.config import settings


@tool
async def create_linear_task(title: str, description: str = "", team_id: str = "") -> str:
    """Создать задачу в Linear.

    Args:
        title: Название задачи
        description: Описание задачи
        team_id: ID команды в Linear

    Returns:
        Результат создания задачи
    """
    if not settings.linear_api_key:
        return "Интеграция не настроена: отсутствует LINEAR_API_KEY"

    from ai_office.integrations.linear import create_linear_issue

    result = await create_linear_issue(title=title, description=description, team_id=team_id)

    if "error" in result:
        return f"Ошибка создания задачи в Linear: {result['error']}"

    identifier = result.get("identifier", "")
    url = result.get("url", "")
    return f"Задача создана в Linear: {identifier} - {title}\nСсылка: {url}"


@tool
async def list_linear_tasks(team_id: str = "", status: str = "") -> str:
    """Получить список задач из Linear.

    Args:
        team_id: ID команды для фильтрации
        status: Статус для фильтрации

    Returns:
        Список задач в текстовом формате
    """
    if not settings.linear_api_key:
        return "Интеграция не настроена: отсутствует LINEAR_API_KEY"

    from ai_office.integrations.linear import list_linear_issues

    issues = await list_linear_issues(team_id=team_id, status=status or None)

    if not issues:
        return "Задачи не найдены в Linear."

    lines = ["Задачи в Linear:"]
    for issue in issues[:20]:
        identifier = issue.get("identifier", "")
        title = issue.get("title", "")
        state = issue.get("state", {}).get("name", "")
        lines.append(f"  {identifier} [{state}]: {title}")

    return "\n".join(lines)


@tool
async def create_notion_note(title: str, content: str = "") -> str:
    """Создать заметку в Notion.

    Args:
        title: Заголовок заметки
        content: Содержимое заметки

    Returns:
        Результат создания заметки
    """
    if not settings.notion_api_key:
        return "Интеграция не настроена: отсутствует NOTION_API_KEY"

    if not settings.notion_database_id:
        return "Интеграция не настроена: отсутствует NOTION_DATABASE_ID"

    from ai_office.integrations.notion import create_notion_page

    result = await create_notion_page(
        database_id=settings.notion_database_id,
        title=title,
        content=content,
    )

    if "error" in result:
        return f"Ошибка создания заметки в Notion: {result['error']}"

    page_url = result.get("url", "")
    return f"Заметка создана в Notion: '{title}'\nСсылка: {page_url}"


@tool
async def search_notion_database(query: str = "") -> str:
    """Поиск в базе данных Notion.

    Args:
        query: Текст для поиска (фильтр по названию)

    Returns:
        Результаты поиска в текстовом формате
    """
    if not settings.notion_api_key:
        return "Интеграция не настроена: отсутствует NOTION_API_KEY"

    if not settings.notion_database_id:
        return "Интеграция не настроена: отсутствует NOTION_DATABASE_ID"

    from ai_office.integrations.notion import query_notion_database

    filter_dict = None
    if query:
        filter_dict = {
            "property": "Name",
            "title": {"contains": query},
        }

    results = await query_notion_database(
        database_id=settings.notion_database_id,
        filter_dict=filter_dict,
    )

    if not results:
        return "Записи не найдены в Notion."

    lines = ["Записи в Notion:"]
    for page in results[:20]:
        props = page.get("properties", {})
        name_prop = props.get("Name", {}).get("title", [])
        title = name_prop[0].get("text", {}).get("content", "Без названия") if name_prop else "Без названия"
        url = page.get("url", "")
        lines.append(f"  - {title} ({url})")

    return "\n".join(lines)
