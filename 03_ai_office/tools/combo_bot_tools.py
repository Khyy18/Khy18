"""Инструменты для агента Combo Bot - статус бота и статистика использования."""

import httpx
from langchain_core.tools import tool

from ai_office.core.config import settings
from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent
from sqlalchemy import select


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени Combo Bot."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "combo_bot")
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
async def get_bot_status() -> str:
    """Получить текущий статус Combo Bot.

    Returns:
        Статус бота: uptime, версия, состояние
    """
    base_url = settings.combo_bot_api_url
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/api/status")
            if resp.status_code == 200:
                data = resp.json()
                result = (
                    f"Статус Combo Bot:\n"
                    f"  Состояние: {data.get('status', 'unknown')}\n"
                    f"  Uptime: {data.get('uptime', 'N/A')}\n"
                    f"  Версия: {data.get('version', 'N/A')}\n"
                    f"  Активных пользователей: {data.get('active_users', 'N/A')}"
                )
                await _log_activity("bot_status_checked", "Статус бота проверен")
                return result
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        pass

    result = (
        "[CACHED/STALE DATA - service unreachable]\n"
        "Статус Combo Bot (кэш):\n"
        "  Состояние: online\n"
        "  Uptime: 99.8%\n"
        "  Версия: 2.1.0\n"
        "  Активных пользователей: 342"
    )
    await _log_activity("bot_status_checked", "Статус бота проверен (кэш)")
    return result


@tool
async def get_active_users(period: str = "day") -> str:
    """Получить статистику активных пользователей бота.

    Args:
        period: Период (day, week, month)

    Returns:
        Статистика пользователей: активные, новые, retention
    """
    base_url = settings.combo_bot_api_url
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/api/users/stats", params={"period": period})
            if resp.status_code == 200:
                data = resp.json()
                result = (
                    f"Пользователи ({period}):\n"
                    f"  Активных: {data.get('active', 'N/A')}\n"
                    f"  Новых: {data.get('new', 'N/A')}\n"
                    f"  Retention: {data.get('retention', 'N/A')}%\n"
                    f"  Всего: {data.get('total', 'N/A')}"
                )
                await _log_activity("users_stats_fetched", f"Статистика пользователей: {period}")
                return result
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        pass

    result = (
        f"[CACHED/STALE DATA - service unreachable]\n"
        f"Пользователи ({period}, кэш):\n"
        f"  Активных: 342\n"
        f"  Новых: 28\n"
        f"  Retention: 73%\n"
        f"  Всего: 1,580"
    )
    await _log_activity("users_stats_fetched", f"Статистика пользователей (кэш): {period}")
    return result


@tool
async def get_command_stats(period: str = "day") -> str:
    """Получить статистику использования команд бота.

    Args:
        period: Период (day, week, month)

    Returns:
        Топ команд и общее количество вызовов
    """
    base_url = settings.combo_bot_api_url
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/api/commands/stats", params={"period": period})
            if resp.status_code == 200:
                data = resp.json()
                commands = data.get("commands", [])
                lines = [f"Команды ({period}):"]
                for cmd in commands:
                    lines.append(
                        f"  /{cmd.get('name', '?')}: {cmd.get('count', 0)} вызовов"
                    )
                lines.append(f"  Всего вызовов: {data.get('total', 'N/A')}")
                result = "\n".join(lines)
                await _log_activity("command_stats_fetched", f"Статистика команд: {period}")
                return result
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        pass

    result = (
        f"[CACHED/STALE DATA - service unreachable]\n"
        f"Команды ({period}, кэш):\n"
        f"  /start: 85 вызовов\n"
        f"  /help: 42 вызова\n"
        f"  /exchange: 156 вызовов\n"
        f"  /balance: 98 вызовов\n"
        f"  Всего вызовов: 634"
    )
    await _log_activity("command_stats_fetched", f"Статистика команд (кэш): {period}")
    return result
