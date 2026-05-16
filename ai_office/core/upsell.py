"""Система upsell-триггеров для повышения конверсии подписок."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.models import UpsellEvent, Workspace

# Trigger type constants
TRIGGER_LOCKED_AGENT = "locked_agent"
TRIGGER_MESSAGE_LIMIT_80 = "message_limit_80pct"
TRIGGER_LOCKED_FEATURE = "locked_feature"
TRIGGER_HIGH_ENGAGEMENT = "high_engagement"

# Message limits per tier
_TIER_LIMITS = {
    "free": 100,
    "starter": 1000,
    "pro": 5000,
    "enterprise": 999999,
}


async def check_upsell_triggers(
    workspace_id: int, session: AsyncSession
) -> list[str]:
    """Проверяет все upsell-триггеры для workspace.

    Условия:
    - message_limit_80pct: если использовано >= 80% лимита сообщений

    Args:
        workspace_id: ID рабочего пространства
        session: Асинхронная сессия БД

    Returns:
        Список сработавших trigger_type
    """
    triggered = []

    # Get workspace
    result = await session.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        return triggered

    # Check message limit 80%
    tier = workspace.subscription_tier or "free"
    limit = _TIER_LIMITS.get(tier, 100)
    used = workspace.messages_used_this_month or 0

    if limit > 0 and used >= limit * 0.8:
        triggered.append(TRIGGER_MESSAGE_LIMIT_80)

    return triggered


async def record_upsell_shown(
    workspace_id: int, trigger_type: str, session: AsyncSession
) -> None:
    """Записывает показ upsell-сообщения.

    Args:
        workspace_id: ID рабочего пространства
        trigger_type: Тип триггера
        session: Асинхронная сессия БД
    """
    event = UpsellEvent(workspace_id=workspace_id, trigger_type=trigger_type)
    session.add(event)
    await session.commit()


async def record_conversion(
    workspace_id: int, trigger_type: str, session: AsyncSession
) -> None:
    """Отмечает конверсию по upsell-событию.

    Args:
        workspace_id: ID рабочего пространства
        trigger_type: Тип триггера
        session: Асинхронная сессия БД
    """
    result = await session.execute(
        select(UpsellEvent)
        .where(
            UpsellEvent.workspace_id == workspace_id,
            UpsellEvent.trigger_type == trigger_type,
            UpsellEvent.converted == False,  # noqa: E712
        )
        .order_by(UpsellEvent.shown_at.desc())
        .limit(1)
    )
    event = result.scalar_one_or_none()
    if event:
        event.converted = True
        await session.commit()


async def get_upsell_stats(session: AsyncSession) -> dict:
    """Возвращает статистику upsell-событий.

    Returns:
        dict с total_shown, total_converted, conversion_rate, by_trigger
    """
    # Get all events
    all_events_result = await session.execute(select(UpsellEvent))
    all_events = all_events_result.scalars().all()

    total_shown = len(all_events)
    total_converted = sum(1 for e in all_events if e.converted)

    conversion_rate = (
        round(total_converted / total_shown, 4) if total_shown > 0 else 0.0
    )

    # By trigger
    by_trigger: dict = {}
    for event in all_events:
        trigger = event.trigger_type
        if trigger not in by_trigger:
            by_trigger[trigger] = {"shown": 0, "converted": 0}
        by_trigger[trigger]["shown"] += 1
        if event.converted:
            by_trigger[trigger]["converted"] += 1

    return {
        "total_shown": total_shown,
        "total_converted": total_converted,
        "conversion_rate": conversion_rate,
        "by_trigger": by_trigger,
    }


async def can_show_upsell(
    workspace_id: int, trigger_type: str, session: AsyncSession
) -> bool:
    """Проверяет, можно ли показать upsell (макс. 1 раз в день на workspace/trigger).

    Args:
        workspace_id: ID рабочего пространства
        trigger_type: Тип триггера
        session: Асинхронная сессия БД

    Returns:
        True если можно показать, False если уже показывали сегодня
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)

    result = await session.execute(
        select(func.count(UpsellEvent.id)).where(
            UpsellEvent.workspace_id == workspace_id,
            UpsellEvent.trigger_type == trigger_type,
            UpsellEvent.shown_at >= cutoff,
        )
    )
    count = result.scalar() or 0
    return count == 0
