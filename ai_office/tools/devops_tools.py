"""Инструменты DevOps/SRE инженера - записывают активность в БД."""

from langchain_core.tools import tool
from sqlalchemy import select

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
async def check_deployment_status(service: str) -> str:
    """Проверить статус деплоя сервиса (имитация с логированием в БД).

    Args:
        service: Название сервиса для проверки

    Returns:
        Статус деплоя
    """
    result = (
        f"[Имитация] Статус деплоя сервиса '{service}':\n"
        f"Версия: v1.0.0\n"
        f"Статус: running\n"
        f"Uptime: 99.9%\n"
        f"Последний деплой: успешен"
    )
    await _log_activity("deployment_checked", f"Проверка деплоя: {service}")
    return result


@tool
async def run_health_check(endpoint: str) -> str:
    """Запустить health check для эндпоинта (имитация с логированием в БД).

    Args:
        endpoint: URL эндпоинта для проверки

    Returns:
        Результат проверки здоровья
    """
    result = (
        f"[Имитация] Health check для '{endpoint}':\n"
        f"HTTP Status: 200 OK\n"
        f"Response time: 45ms\n"
        f"Все зависимости доступны"
    )
    await _log_activity("health_check", f"Health check: {endpoint}")
    return result


@tool
async def analyze_logs(service: str, timeframe: str) -> str:
    """Анализировать логи сервиса (имитация с логированием в БД).

    Args:
        service: Название сервиса
        timeframe: Временной интервал для анализа (например, '1h', '24h')

    Returns:
        Результат анализа логов
    """
    result = (
        f"[Имитация] Анализ логов сервиса '{service}' за {timeframe}:\n"
        f"Всего записей: 1024\n"
        f"Ошибок: 3 (0.3%)\n"
        f"Предупреждений: 12\n"
        f"Паттерн: стабильная работа, единичные таймауты к внешнему API"
    )
    await _log_activity("logs_analyzed", f"Анализ логов: {service} ({timeframe})")
    return result
