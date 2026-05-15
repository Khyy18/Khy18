"""Optimizer worker tasks for ARQ queue."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from core.config import settings

logger = logging.getLogger(__name__)


def _build_fallback_llm_client():
    """Build a FallbackLLMClient from settings, matching main.py's approach."""
    from core.llm import FallbackLLMClient

    provider_configs = {
        "openai": {
            "provider": "openai",
            "api_key": settings.openai_api_key,
            "model": settings.llm_openai_model,
            "timeout": settings.llm_openai_timeout,
        },
        "anthropic": {
            "provider": "anthropic",
            "api_key": settings.anthropic_api_key,
            "model": settings.llm_anthropic_model,
            "timeout": settings.llm_anthropic_timeout,
        },
        "groq": {
            "provider": "groq",
            "api_key": settings.groq_api_key,
            "model": settings.llm_groq_model,
            "timeout": settings.llm_groq_timeout,
        },
    }
    chain_names = [
        p.strip()
        for p in settings.llm_fallback_chain.split(",")
        if p.strip()
    ]
    fallback_providers = [
        provider_configs[name]
        for name in chain_names
        if name in provider_configs
    ]

    return FallbackLLMClient(
        providers=fallback_providers,
        redis_url=settings.redis_url,
    )


async def check_significance_task(
    ctx: dict[str, Any],
    test_id: str,
) -> dict[str, Any]:
    """Check statistical significance for an A/B test."""
    from core.db import async_session_factory
    from agents.optimizer import OptimizerAgent

    llm_client = _build_fallback_llm_client()
    optimizer = OptimizerAgent(
        llm_client=llm_client,
        session_factory=async_session_factory,
        redis_url=settings.redis_url,
    )
    try:
        result = await optimizer.check_significance(UUID(test_id))
        logger.info("Check significance task completed for test %s: %s", test_id, result)
        return result
    finally:
        await llm_client.close()


async def generate_variants_task(
    ctx: dict[str, Any],
    campaign_id: str,
    tenant_id: str,
    name: str,
    variants: int,
    min_sends: int,
) -> dict[str, Any]:
    """Generate A/B test variants for a campaign."""
    from core.db import async_session_factory
    from agents.optimizer import OptimizerAgent

    llm_client = _build_fallback_llm_client()
    optimizer = OptimizerAgent(
        llm_client=llm_client,
        session_factory=async_session_factory,
        redis_url=settings.redis_url,
    )
    try:
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
    finally:
        await llm_client.close()
