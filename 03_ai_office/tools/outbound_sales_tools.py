"""Инструменты для агента Outbound Sales - управление кампаниями и статистика."""

from langchain_core.tools import tool

from ai_office.core.database import async_session
from ai_office.core.models import ActivityLog, Agent
from sqlalchemy import select


async def _log_activity(action_type: str, description: str) -> None:
    """Записать активность в БД от имени Outbound Sales."""
    async with async_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.name == "outbound_sales")
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
async def get_campaign_status(campaign_id: str = "") -> str:
    """Получить статус кампаний outbound sales.

    Args:
        campaign_id: ID конкретной кампании (если пусто - все активные)

    Returns:
        Статус кампании или список активных кампаний
    """
    if campaign_id:
        result = (
            f"Кампания {campaign_id}:\n"
            f"  Статус: активна\n"
            f"  Отправлено: 150 писем\n"
            f"  Открыто: 45 (30%)\n"
            f"  Ответов: 12 (8%)\n"
            f"  Встреч назначено: 3"
        )
    else:
        result = (
            "Активные кампании:\n"
            "  1. campaign_001 - B2B SaaS outreach (активна)\n"
            "  2. campaign_002 - Enterprise follow-up (на паузе)\n"
            "  3. campaign_003 - New market segment (завершена)"
        )

    await _log_activity("campaign_status_checked", f"Проверка статуса: {campaign_id or 'все'}")
    return result


@tool
async def start_campaign(campaign_name: str, target_segment: str) -> str:
    """Запустить новую outbound кампанию.

    Args:
        campaign_name: Название кампании
        target_segment: Целевой сегмент аудитории

    Returns:
        Подтверждение запуска кампании
    """
    result = (
        f"Кампания '{campaign_name}' запущена:\n"
        f"  Сегмент: {target_segment}\n"
        f"  Статус: активна\n"
        f"  Каналы: email, голосовые звонки\n"
        f"  Расписание: пн-пт, 10:00-18:00 MSK"
    )

    await _log_activity("campaign_started", f"Запуск кампании: {campaign_name}")
    return result


@tool
async def get_sales_stats(period: str = "week") -> str:
    """Получить сводную статистику продаж.

    Args:
        period: Период статистики (day, week, month)

    Returns:
        Сводная статистика: лиды, встречи, конверсия
    """
    period_label = {"day": "за день", "week": "за неделю", "month": "за месяц"}.get(
        period, "за неделю"
    )

    result = (
        f"Статистика outbound sales {period_label}:\n"
        f"  Отправлено писем: 450\n"
        f"  Открытий: 180 (40%)\n"
        f"  Ответов: 36 (8%)\n"
        f"  Назначено встреч: 9\n"
        f"  Закрыто сделок: 2\n"
        f"  Конверсия (письмо -> сделка): 0.4%\n"
        f"  Bounce rate: 2.1%\n"
        f"  Deliverability: 97.9%"
    )

    await _log_activity("sales_stats_fetched", f"Статистика запрошена: {period}")
    return result
