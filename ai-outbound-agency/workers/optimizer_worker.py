"""Optimizer worker tasks for ARQ queue."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from core.config import settings

logger = logging.getLogger(__name__)


async def check_significance_task(
    ctx: dict[str, Any],
    test_id: str,
) -> dict[str, Any]:
    """Check statistical significance for an A/B test."""
    from core.llm import LLMClient
    from core.db import async_session_factory
    from agents.optimizer import OptimizerAgent

    llm_client = LLMClient(
        provider="openai",
        api_key=settings.openai_api_key,
        model="gpt-4",
    )
    optimizer = OptimizerAgent(
        llm_client=llm_client,
        session_factory=async_session_factory,
        redis_url=settings.redis_url,
    )
    result = await optimizer.check_significance(UUID(test_id))
    logger.info("Check significance task completed for test %s: %s", test_id, result)
    return result


async def generate_variants_task(
    ctx: dict[str, Any],
    campaign_id: str,
    tenant_id: str,
    name: str,
    variants: int,
    min_sends: int,
) -> dict[str, Any]:
    """Generate A/B test variants for a campaign."""
    from core.llm import LLMClient
    from core.db import async_session_factory
    from agents.optimizer import OptimizerAgent

    llm_client = LLMClient(
        provider="openai",
        api_key=settings.openai_api_key,
        model="gpt-4",
    )
    optimizer = OptimizerAgent(
        llm_client=llm_client,
        session_factory=async_session_factory,
        redis_url=settings.redis_url,
    )
    result = await optimizer.create_test(
        campaign_id=UUID(campaign_id),
        tenant_id=UUID(tenant_id),
        name=name,
        variants=variants,
        min_sends_per_variant=min_sends,
    )
    logger.info(
        "Generate variants task completed for campaign %s: %s",
        campaign_id,
        result,
    )
    return result
