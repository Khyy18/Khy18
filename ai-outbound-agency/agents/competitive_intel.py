"""Competitive intelligence agent: monitors competitor landscape and market sentiment."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.models import CompetitiveIntel

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 24 * 3600  # 24 hours


class CompetitiveIntelAgent:
    """Monitors competitor landscape and market sentiment automatically."""

    DEFAULT_COMPETITORS = [
        {
            "name": "Instantly.ai",
            "pricing_url": "https://instantly.ai/pricing",
            "changelog_url": "https://instantly.ai/blog",
        },
        {
            "name": "Smartlead.ai",
            "pricing_url": "https://smartlead.ai/pricing",
            "changelog_url": "https://smartlead.ai/blog",
        },
        {
            "name": "Apollo.io",
            "pricing_url": "https://www.apollo.io/pricing",
            "changelog_url": "https://www.apollo.io/blog",
        },
    ]

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

    def _cache_key(self, url: str) -> str:
        """Generate a Redis cache key for a URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return f"competitive_intel:last_scrape:{url_hash}"

    async def _is_cached(self, url: str) -> bool:
        """Check if a URL was scraped within the last 24 hours."""
        if not self._redis:
            return False
        key = self._cache_key(url)
        val = await self._redis.get(key)
        return val is not None

    async def _mark_cached(self, url: str) -> None:
        """Mark a URL as recently scraped with a 24h TTL."""
        if not self._redis:
            return
        key = self._cache_key(url)
        await self._redis.setex(key, CACHE_TTL_SECONDS, "1")

    async def scrape_pricing(
        self, competitor_name: str, url: str
    ) -> dict[str, Any]:
        """Fetch competitor pricing page, extract and store pricing info.

        Returns {"success": True, "summary": ...} or {"success": False, "error": ...}.
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url)
                response.raise_for_status()
                raw_text = response.text[:5000]
        except Exception as e:
            logger.error("Failed to scrape pricing for %s: %s", competitor_name, str(e))
            return {"success": False, "error": str(e)}

        # Summarize via LLM if available
        summary = None
        if self._llm:
            try:
                prompt = (
                    f"Summarize the pricing tiers from this page content for "
                    f"{competitor_name}:\n\n{raw_text[:2000]}"
                )
                summary = await self._llm.generate(prompt)
            except Exception as e:
                logger.warning("LLM summarization failed: %s", str(e))

        # Store in database
        async with self._session_factory() as session:
            record = CompetitiveIntel(
                source=url,
                category="pricing",
                content=raw_text,
                summary=summary,
                competitor_name=competitor_name,
            )
            session.add(record)
            await session.commit()

        await self._mark_cached(url)
        return {"success": True, "summary": summary or "No LLM summary available"}

    async def scrape_changelog(
        self, competitor_name: str, url: str
    ) -> dict[str, Any]:
        """Fetch competitor changelog/blog page, extract and store feature info.

        Returns {"success": True, "summary": ...} or {"success": False, "error": ...}.
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url)
                response.raise_for_status()
                raw_text = response.text[:5000]
        except Exception as e:
            logger.error("Failed to scrape changelog for %s: %s", competitor_name, str(e))
            return {"success": False, "error": str(e)}

        # Summarize via LLM if available
        summary = None
        if self._llm:
            try:
                prompt = (
                    f"Summarize the recent feature updates from this page for "
                    f"{competitor_name}:\n\n{raw_text[:2000]}"
                )
                summary = await self._llm.generate(prompt)
            except Exception as e:
                logger.warning("LLM summarization failed: %s", str(e))

        # Store in database
        async with self._session_factory() as session:
            record = CompetitiveIntel(
                source=url,
                category="features",
                content=raw_text,
                summary=summary,
                competitor_name=competitor_name,
            )
            session.add(record)
            await session.commit()

        await self._mark_cached(url)
        return {"success": True, "summary": summary or "No LLM summary available"}

    async def monitor_sentiment(self, source: str = "reddit") -> dict[str, Any]:
        """Placeholder for sentiment monitoring (requires Reddit API integration).

        Stores a placeholder record and returns success.
        """
        async with self._session_factory() as session:
            record = CompetitiveIntel(
                source=source,
                category="sentiment",
                content="Sentiment monitoring placeholder - requires Reddit API integration",
                summary=None,
                competitor_name=None,
            )
            session.add(record)
            await session.commit()

        return {
            "success": True,
            "source": source,
            "note": "Sentiment monitoring placeholder - requires Reddit API integration",
        }

    async def check_brand_mentions(self, brand_name: str) -> dict[str, Any]:
        """Placeholder for brand mention monitoring.

        Stores a placeholder record and returns success.
        """
        async with self._session_factory() as session:
            record = CompetitiveIntel(
                source="brand_monitoring",
                category="brand_mention",
                content=f"Brand mention check placeholder for: {brand_name}",
                summary=None,
                competitor_name=brand_name,
            )
            session.add(record)
            await session.commit()

        return {
            "success": True,
            "brand_name": brand_name,
            "note": "Brand mention monitoring placeholder - requires API integration",
        }

    async def generate_weekly_digest(
        self, session: AsyncSession
    ) -> dict[str, Any]:
        """Query recent CompetitiveIntel records and generate a digest summary.

        Returns {"entries_count": N, "digest": "..."}.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        stmt = select(CompetitiveIntel).where(
            CompetitiveIntel.created_at >= cutoff
        )
        result = await session.execute(stmt)
        entries = result.scalars().all()

        entries_count = len(entries)
        if entries_count == 0:
            return {"entries_count": 0, "digest": "No competitive intelligence data in the last 7 days."}

        # Build digest
        digest_parts = []
        for entry in entries:
            part = f"[{entry.category}] {entry.competitor_name or 'Unknown'}: {entry.summary or entry.content[:200]}"
            digest_parts.append(part)

        raw_digest = "\n".join(digest_parts)

        # Summarize with LLM if available
        if self._llm:
            try:
                prompt = (
                    f"Summarize this weekly competitive intelligence digest:\n\n"
                    f"{raw_digest[:3000]}"
                )
                digest_text = await self._llm.generate(prompt)
            except Exception:
                digest_text = raw_digest
        else:
            digest_text = raw_digest

        return {"entries_count": entries_count, "digest": digest_text}
