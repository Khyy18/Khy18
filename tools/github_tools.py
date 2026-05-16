"""Инструменты интеграции с GitHub - записывают активность в БД."""

import httpx
from langchain_core.tools import tool
from sqlalchemy import select

from ai_office.core.config import settings
from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени Nova."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "Nova")
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
async def create_github_issue(repo: str, title: str, body: str, labels: str = "") -> str:
    """Создать issue в GitHub репозитории.

    Args:
        repo: Репозиторий в формате owner/repo
        title: Заголовок issue
        body: Описание issue
        labels: Метки через запятую (опционально)

    Returns:
        Результат создания issue
    """
    token = settings.github_token
    if not token:
        return "GITHUB_TOKEN не настроен. Установите переменную окружения."

    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload = {"title": title, "body": body}
    if labels:
        payload["labels"] = [l.strip() for l in labels.split(",")]

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)

    if response.status_code == 201:
        data = response.json()
        result = f"Issue создан: #{data['number']} - {data['title']}\nURL: {data['html_url']}"
    else:
        error_detail = response.text[:150] if response.text else "Нет деталей"
        result = f"Ошибка GitHub API (HTTP {response.status_code}): {error_detail}"

    await _log_activity("github_issue_created", f"Создан issue в {repo}: {title}")
    return result


@tool
async def list_github_issues(repo: str, state: str = "open") -> str:
    """Получить список issues из GitHub репозитория.

    Args:
        repo: Репозиторий в формате owner/repo
        state: Статус issues (open, closed, all)

    Returns:
        Список issues
    """
    token = settings.github_token
    if not token:
        return "GITHUB_TOKEN не настроен. Установите переменную окружения."

    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    params = {"state": state}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)

    if response.status_code == 200:
        issues = response.json()
        if not issues:
            result = f"В {repo} нет issues со статусом '{state}'."
        else:
            lines = [f"Issues в {repo} ({state}):"]
            for issue in issues[:20]:
                lines.append(f"  #{issue['number']} - {issue['title']} [{issue['state']}]")
            result = "\n".join(lines)
    else:
        error_detail = response.text[:150] if response.text else "Нет деталей"
        result = f"Ошибка GitHub API (HTTP {response.status_code}): {error_detail}"

    await _log_activity("github_issues_listed", f"Список issues {repo} ({state})")
    return result


@tool
async def create_pull_request_comment(repo: str, pr_number: int, body: str) -> str:
    """Оставить комментарий к Pull Request в GitHub.

    Args:
        repo: Репозиторий в формате owner/repo
        pr_number: Номер Pull Request
        body: Текст комментария

    Returns:
        Результат добавления комментария
    """
    token = settings.github_token
    if not token:
        return "GITHUB_TOKEN не настроен. Установите переменную окружения."

    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload = {"body": body}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)

    if response.status_code == 201:
        data = response.json()
        result = f"Комментарий добавлен к PR #{pr_number}\nURL: {data['html_url']}"
    else:
        error_detail = response.text[:150] if response.text else "Нет деталей"
        result = f"Ошибка GitHub API (HTTP {response.status_code}): {error_detail}"

    await _log_activity("github_pr_commented", f"Комментарий к PR #{pr_number} в {repo}")
    return result
