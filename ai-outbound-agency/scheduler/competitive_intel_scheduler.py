"""Scheduler for competitive intelligence data collection."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.competitive_intel import CompetitiveIntelAgent

logger = logging.getLogger(__name__)


class CompetitiveIntelScheduler:
    """Orchestrates periodic competitive intelligence scraping."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        llm_client: Any | None = None,
        settings: Any | None = None,
        redis_client: Any | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._llm = llm_client
        self._settings = settings
        self._redis = redis_client
        self._agent = CompetitiveIntelAgent(
            session_factory=session_factory,
            llm_client=llm_client,
            settings=settings,
            redis_client=redis_client,
        )

    async def run_weekly_tick(self) -> dict[str, Any]:
        """Run weekly competitive intelligence collection.

        Loops through DEFAULT_COMPETITORS, checks cache, and scrapes pricing
        and changelog for uncached competitors.

        Returns {"competitors_checked": N, "scraped": N, "cached_skipped": N}.
        """
        competitors = CompetitiveIntelAgent.DEFAULT_COMPETITORS
        competitors_checked = 0
        scraped = 0
        cached_skipped = 0

        for competitor in competitors:
            competitors_checked += 1
            name = competitor["name"]
            pricing_url = competitor["pricing_url"]
            changelog_url = competitor["changelog_url"]

            # Check and scrape pricing
            if await self._agent._is_cached(pricing_url):
                cached_skipped += 1
                logger.debug("Skipping cached pricing for %s", name)
            else:
                result = await self._agent.scrape_pricing(name, pricing_url)
                if result.get("success"):
                    scraped += 1

            # Check and scrape changelog
            if await self._agent._is_cached(changelog_url):
                cached_skipped += 1
                logger.debug("Skipping cached changelog for %s", name)
            else:
                result = await self._agent.scrape_changelog(name, changelog_url)
                if result.get("success"):
                    scraped += 1

        logger.info(
            "Competitive intel tick: checked=%d, scraped=%d, cached_skipped=%d",
            competitors_checked,
            scraped,
            cached_skipped,
        )

        return {
            "competitors_checked": competitors_checked,
            "scraped": scraped,
            "cached_skipped": cached_skipped,
        }
