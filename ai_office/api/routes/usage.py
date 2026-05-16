"""Эндпоинт для статистики использования токенов."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_office.core.config import settings
from ai_office.core.database import get_session
from ai_office.core.models import TokenUsage
from ai_office.core.rate_limiter import budget_tracker

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
async def get_usage(session: AsyncSession = Depends(get_session)):
    """Получить статистику использования токенов за сегодня."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Total today
    total_query = select(
        func.coalesce(func.sum(TokenUsage.prompt_tokens), 0).label("prompt_tokens"),
        func.coalesce(func.sum(TokenUsage.completion_tokens), 0).label("completion_tokens"),
        func.coalesce(func.sum(TokenUsage.estimated_cost_usd), 0.0).label("total_cost"),
    ).where(TokenUsage.timestamp >= today_start)

    result = await session.execute(total_query)
    total_row = result.one()

    # Per-agent breakdown
    agent_query = (
        select(
            TokenUsage.agent_name,
            func.sum(TokenUsage.prompt_tokens).label("prompt_tokens"),
            func.sum(TokenUsage.completion_tokens).label("completion_tokens"),
            func.sum(TokenUsage.estimated_cost_usd).label("cost"),
            func.count(TokenUsage.id).label("calls"),
        )
        .where(TokenUsage.timestamp >= today_start)
        .group_by(TokenUsage.agent_name)
    )
    agent_result = await session.execute(agent_query)
    per_agent = [
        {
            "agent_name": row.agent_name,
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "cost": round(row.cost, 6),
            "calls": row.calls,
        }
        for row in agent_result.all()
    ]

    # Per-provider breakdown
    provider_query = (
        select(
            TokenUsage.provider,
            func.sum(TokenUsage.prompt_tokens).label("prompt_tokens"),
            func.sum(TokenUsage.completion_tokens).label("completion_tokens"),
            func.sum(TokenUsage.estimated_cost_usd).label("cost"),
            func.count(TokenUsage.id).label("calls"),
        )
        .where(TokenUsage.timestamp >= today_start)
        .group_by(TokenUsage.provider)
    )
    provider_result = await session.execute(provider_query)
    per_provider = [
        {
            "provider": row.provider,
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "cost": round(row.cost, 6),
            "calls": row.calls,
        }
        for row in provider_result.all()
    ]

    daily_budget = settings.daily_budget_usd
    today_spend = await budget_tracker.get_today_spend()

    return {
        "total_today": {
            "prompt_tokens": total_row.prompt_tokens,
            "completion_tokens": total_row.completion_tokens,
            "total_cost": round(total_row.total_cost, 6),
            "total_tokens": total_row.prompt_tokens + total_row.completion_tokens,
        },
        "per_agent": per_agent,
        "per_provider": per_provider,
        "daily_budget": daily_budget,
        "budget_remaining": round(daily_budget - today_spend, 6),
    }
