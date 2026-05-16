"""Optimizer API routes for A/B testing and campaign optimization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import ABTest, ABTestStatus, User
from dashboard.auth import get_current_user
from dashboard.schemas import (
    ABTestCreate,
    ABTestListResponse,
    ABTestResponse,
    ABTestResultsResponse,
    SendTimeResponse,
    SuggestionResponse,
)

if TYPE_CHECKING:
    from agents.optimizer import OptimizerAgent

router = APIRouter(prefix="/api/optimizer", tags=["optimizer"])

_optimizer_instance: OptimizerAgent | None = None


async def _get_session():
    from core.db import get_session as _gs

    async for session in _gs():
        yield session


def _get_optimizer() -> OptimizerAgent:
    """Get or create the cached OptimizerAgent instance."""
    global _optimizer_instance
    if _optimizer_instance is None:
        from core.config import settings
        from core.db import async_session_factory
        from core.llm import LLMClient

        llm_client = LLMClient(
            provider="openai",
            api_key=settings.openai_api_key,
            model="gpt-4",
        )
        _optimizer_instance = OptimizerAgent(
            llm_client=llm_client,
            session_factory=async_session_factory,
            redis_url=settings.redis_url,
        )
    return _optimizer_instance


@router.get("/tests", response_model=ABTestListResponse)
async def list_tests(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """List active A/B tests for the current tenant."""
    base_query = select(ABTest).where(ABTest.tenant_id == current_user.tenant_id)
    count_query = (
        select(func.count())
        .select_from(ABTest)
        .where(ABTest.tenant_id == current_user.tenant_id)
    )

    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    result = await session.execute(
        base_query.order_by(ABTest.created_at.desc()).limit(limit).offset(offset)
    )
    items = list(result.scalars().all())

    return {"items": items, "total": total}


@router.post("/tests", response_model=ABTestResponse, status_code=status.HTTP_201_CREATED)
async def create_test(
    data: ABTestCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> ABTest:
    """Create a new A/B test."""
    optimizer = _get_optimizer()
    test = await optimizer.create_ab_test(
        campaign_id=data.campaign_id,
        tenant_id=current_user.tenant_id,
        name=data.name,
        variants=[v.model_dump() for v in data.variants],
        min_sends=data.min_sends_per_variant,
        session=session,
    )
    await session.commit()
    return test


@router.get("/tests/{test_id}/results", response_model=ABTestResultsResponse)
async def get_test_results(
    test_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get test results with significance check."""
    # Verify test belongs to tenant
    result = await session.execute(
        select(ABTest).where(
            ABTest.id == test_id,
            ABTest.tenant_id == current_user.tenant_id,
        )
    )
    test = result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    optimizer = _get_optimizer()
    significance = await optimizer.check_significance(test_id, session)

    return {
        "test_id": str(test_id),
        "status": test.status.value if hasattr(test.status, "value") else str(test.status),
        "variants": significance.get("variant_stats", []),
        "is_significant": significance["is_significant"],
        "p_value": significance["p_value"],
        "winner_key": significance.get("winner_key"),
    }


@router.post("/tests/{test_id}/promote")
async def promote_test(
    test_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Manually promote a winning variant."""
    # Verify test belongs to tenant
    result = await session.execute(
        select(ABTest).where(
            ABTest.id == test_id,
            ABTest.tenant_id == current_user.tenant_id,
        )
    )
    test = result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    if test.status == ABTestStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Test is already completed",
        )

    optimizer = _get_optimizer()
    winner_info = await optimizer.promote_winner(test_id, session)
    await session.commit()
    return winner_info


@router.get("/suggestions/{campaign_id}", response_model=SuggestionResponse)
async def get_suggestions(
    campaign_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get AI improvement suggestions for a campaign."""
    optimizer = _get_optimizer()
    suggestions = await optimizer.suggest_improvements(campaign_id, session)
    return {"suggestions": suggestions}


@router.get("/send-times/{tenant_id}", response_model=SendTimeResponse)
async def get_send_times(
    tenant_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> dict:
    """Get optimal send time analysis for a tenant."""
    # Ensure the user can only access their own tenant data
    if current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    optimizer = _get_optimizer()
    optimal_times = await optimizer.optimize_send_times(tenant_id, session)
    return {"optimal_times": optimal_times}
