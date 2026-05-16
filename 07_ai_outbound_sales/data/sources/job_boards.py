"""Job boards data source - searches for company job postings."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import aiohttp
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_CACHE_TTL = 7 * 24 * 3600


class JobBoardsClient:
    """Searches for company job postings to detect hiring signals."""

    SEARCH_URL = "https://html.duckduckgo.com/html/"

    def __init__(
        self,
        redis_url: str,
        max_requests_per_minute: int = 10,
    ) -> None:
        self._redis_url = redis_url
        self._max_requests_per_minute = max_requests_per_minute
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url)
        return self._redis

    async def search_jobs(self, company_name: str) -> list[dict[str, Any]]:
        """Search for job postings from a company.

        Returns list of:
            {"title": "Senior Backend Engineer", "description": "...", "url": "..."}

        Uses Redis cache (7-day TTL). Rate-limited.
        """
        # Check cache first
        cached = await self._check_cache(company_name)
        if cached is not None:
            return cached

        # Rate limit check
        if not await self._rate_limit_check():
            logger.warning("Rate limit reached for job board lookups")
            return []

        # Search for job postings using multiple queries
        queries = [
            f"{company_name} hiring jobs",
            f"{company_name} careers open positions",
        ]

        all_results: list[dict[str, Any]] = []
        for query in queries:
            html = await self._search_web(query)
            if html:
                results = self._parse_job_results(html)
                all_results.extend(results)

        # Deduplicate by title
        seen_titles: set[str] = set()
        unique_results: list[dict[str, Any]] = []
        for item in all_results:
            title_lower = item["title"].lower()
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                unique_results.append(item)

        # Cache results
        await self._save_cache(company_name, unique_results)

        return unique_results

    async def _check_cache(self, company_name: str) -> list[dict[str, Any]] | None:
        """Check Redis cache for existing job data."""
        try:
            redis = await self._get_redis()
            key = f"jobboards:{company_name.lower().replace(' ', '_')}"
            data = await redis.get(key)
            if data:
                return json.loads(data)
        except Exception as exc:
            logger.debug("Cache check failed for %s: %s", company_name, exc)
        return None

    async def _save_cache(self, company_name: str, data: list[dict[str, Any]]) -> None:
        """Save job data to Redis cache."""
        try:
            redis = await self._get_redis()
            key = f"jobboards:{company_name.lower().replace(' ', '_')}"
            await redis.setex(key, _CACHE_TTL, json.dumps(data))
        except Exception as exc:
            logger.debug("Cache save failed for %s: %s", company_name, exc)

    async def _rate_limit_check(self) -> bool:
        """Check if rate limit allows another request."""
        try:
            redis = await self._get_redis()
            key = "ratelimit:jobboards"
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 60)
            return count <= self._max_requests_per_minute
        except Exception as exc:
            logger.debug("Rate limit check failed: %s", exc)
            return True

    async def _search_web(self, query: str) -> str:
        """Perform DuckDuckGo HTML search (same pattern as enricher.py)."""
        try:
            params = {"q": query}
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; SalesBot/1.0)"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.SEARCH_URL,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        return ""
                    return await response.text()
        except Exception as exc:
            logger.debug("Web search failed for '%s': %s", query, exc)
            return ""

    def _parse_job_results(self, html: str) -> list[dict[str, Any]]:
        """Parse search results to extract job titles and descriptions."""
        results: list[dict[str, Any]] = []

        # Extract result entries from DuckDuckGo HTML
        # Each result has a title link and a snippet
        title_parts = html.split("result__a")
        for part in title_parts[1:10]:  # Up to 9 results
            title = ""
            url = ""
            description = ""

            # Extract URL from href
            href_match = re.search(r'href="([^"]*)"', part)
            if href_match:
                url = href_match.group(1)

            # Extract title text
            title_start = part.find(">")
            if title_start != -1:
                title_end = part.find("</a", title_start)
                if title_end == -1:
                    title_end = title_start + 200
                raw_title = part[title_start + 1:title_end]
                # Clean HTML tags
                title = re.sub(r"<[^>]+>", "", raw_title).strip()

            # Extract snippet/description
            snippet_marker = "result__snippet"
            snippet_idx = part.find(snippet_marker)
            if snippet_idx != -1:
                snip_start = part.find(">", snippet_idx)
                if snip_start != -1:
                    snip_end = part.find("</", snip_start)
                    if snip_end == -1:
                        snip_end = snip_start + 300
                    raw_snippet = part[snip_start + 1:snip_end]
                    description = re.sub(r"<[^>]+>", "", raw_snippet).strip()

            if title:
                results.append({
                    "title": title,
                    "description": description,
                    "url": url,
                })

        return results

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
