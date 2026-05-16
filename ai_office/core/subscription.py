"""Подсистема подписок и лимитов для AI Office."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.models import Workspace

TIERS = {
    "free": {
        "allowed_agents": ["alice", "sam"],
        "message_limit": 100,
        "max_users": 1,
    },
    "pro": {
        "allowed_agents": ["alice", "sam", "max", "eva", "leo", "nova", "iris", "oscar"],
        "message_limit": None,  # unlimited
        "max_users": 1,
    },
    "team": {
        "allowed_agents": ["alice", "sam", "max", "eva", "leo", "nova", "iris", "oscar"],
        "message_limit": None,
        "max_users": 5,
    },
}


async def check_access(workspace_id: int, agent_name: str, session: AsyncSession) -> dict:
    """Проверить доступ агента для данного workspace по подписке.

    Returns:
        {"allowed": bool, "reason": str or None}
    """
    result = await session.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        return {"allowed": False, "reason": "Workspace not found"}

    tier = workspace.subscription_tier or "free"
    tier_config = TIERS.get(tier, TIERS["free"])
    allowed_agents = tier_config["allowed_agents"]

    if agent_name.lower() in allowed_agents:
        return {"allowed": True, "reason": None}
    else:
        return {
            "allowed": False,
            "reason": f"Agent '{agent_name}' not available on '{tier}' tier",
        }


async def check_message_limit(workspace_id: int, session: AsyncSession) -> dict:
    """Проверить лимит сообщений для workspace.

    Returns:
        {"remaining": int or None, "limit": int or None, "used": int}
        None for unlimited.
    """
    result = await session.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        return {"remaining": 0, "limit": 0, "used": 0}

    tier = workspace.subscription_tier or "free"
    tier_config = TIERS.get(tier, TIERS["free"])
    limit = tier_config["message_limit"]
    used = workspace.messages_used_this_month or 0

    if limit is None:
        return {"remaining": None, "limit": None, "used": used}
    else:
        remaining = max(0, limit - used)
        return {"remaining": remaining, "limit": limit, "used": used}


async def increment_message_count(workspace_id: int, session: AsyncSession) -> None:
    """Увеличить счётчик сообщений для workspace."""
    result = await session.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if workspace is not None:
        workspace.messages_used_this_month = (workspace.messages_used_this_month or 0) + 1
        await session.commit()


async def reset_monthly_counts(session: AsyncSession) -> None:
    """Сбросить ежемесячные счётчики сообщений для всех workspaces."""
    await session.execute(
        update(Workspace).values(messages_used_this_month=0)
    )
    await session.commit()


async def get_subscription_status(workspace_id: int, session: AsyncSession) -> dict:
    """Получить полную информацию о подписке workspace.

    Returns:
        {"tier": str, "messages_remaining": int or None, "messages_limit": int or None,
         "messages_used": int, "agents_available": list[str]}
    """
    result = await session.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        return {
            "tier": "free",
            "messages_remaining": 0,
            "messages_limit": 0,
            "messages_used": 0,
            "agents_available": [],
        }

    tier = workspace.subscription_tier or "free"
    tier_config = TIERS.get(tier, TIERS["free"])
    limit = tier_config["message_limit"]
    used = workspace.messages_used_this_month or 0

    if limit is None:
        remaining = None
    else:
        remaining = max(0, limit - used)

    return {
        "tier": tier,
        "messages_remaining": remaining,
        "messages_limit": limit,
        "messages_used": used,
        "agents_available": tier_config["allowed_agents"],
    }
