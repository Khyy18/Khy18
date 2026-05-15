"""Technographic data source - detects technology stack from company domains."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import aiohttp
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Cache TTL: 7 days in seconds
_CACHE_TTL = 7 * 24 * 3600

# Technology detection patterns: maps regex patterns to (technology_name, category)
TECHNOLOGY_PATTERNS: dict[str, tuple[str, str]] = {
    r"react": ("React", "frameworks"),
    r"angular": ("Angular", "frameworks"),
    r"vue\.?js|vue\.min\.js": ("Vue.js", "frameworks"),
    r"jquery": ("jQuery", "frameworks"),
    r"bootstrap": ("Bootstrap", "frameworks"),
    r"next\.js|_next/": ("Next.js", "frameworks"),
    r"nuxt": ("Nuxt.js", "frameworks"),
    r"django": ("Django", "frameworks"),
    r"rails|ruby": ("Ruby on Rails", "frameworks"),
    r"laravel": ("Laravel", "frameworks"),
    r"wordpress|wp-content|wp-includes": ("WordPress", "frameworks"),
    r"shopify": ("Shopify", "frameworks"),
    r"google-analytics|gtag|UA-\d+|G-\w+": ("Google Analytics", "analytics"),
    r"mixpanel": ("Mixpanel", "analytics"),
    r"segment\.com|analytics\.js": ("Segment", "analytics"),
    r"hotjar": ("Hotjar", "analytics"),
    r"amplitude": ("Amplitude", "analytics"),
    r"heap": ("Heap", "analytics"),
    r"cloudflare": ("Cloudflare", "cdn"),
    r"fastly": ("Fastly", "cdn"),
    r"akamai": ("Akamai", "cdn"),
    r"cdn\.jsdelivr": ("jsDelivr", "cdn"),
    r"stripe\.js|js\.stripe\.com": ("Stripe", "other"),
    r"intercom": ("Intercom", "other"),
    r"drift": ("Drift", "other"),
    r"zendesk": ("Zendesk", "other"),
    r"hubspot": ("HubSpot", "crm"),
    r"salesforce|force\.com": ("Salesforce", "crm"),
    r"marketo": ("Marketo", "crm"),
    r"pardot": ("Pardot", "crm"),
    r"python": ("Python", "languages"),
    r"node\.js|nodejs": ("Node.js", "languages"),
    r"\.php": ("PHP", "languages"),
    r"java(?!script)": ("Java", "languages"),
    r"\.aspx|\.NET|aspnet": (".NET", "languages"),
    r"typescript|\.ts": ("TypeScript", "languages"),
}


class TechnographicClient:
    """Client for technographic data enrichment.

    Attempts to detect a company's technology stack through:
    1. BuiltWith API (if api_key provided)
    2. Web scraping fallback (analyze HTML headers and scripts)
    """

    def __init__(
        self,
        redis_url: str,
        builtwith_api_key: str = "",
        max_requests_per_minute: int = 10,
    ) -> None:
        self._redis_url = redis_url
        self._builtwith_api_key = builtwith_api_key
        self._max_requests_per_minute = max_requests_per_minute
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url)
        return self._redis

    async def get_tech_stack(self, domain: str) -> dict[str, Any]:
        """Get technology stack for a domain.

        Returns:
            {
                "languages": ["Python", "JavaScript"],
                "frameworks": ["React", "Django"],
                "cdn": ["Cloudflare"],
                "analytics": ["Google Analytics", "Mixpanel"],
                "crm": ["Salesforce", "HubSpot"],
                "other": ["Stripe", "Intercom"]
            }

        Uses Redis cache (7-day TTL). Rate-limited.
        """
        # Check cache first
        cached = await self._check_cache(domain)
        if cached is not None:
            return cached

        # Rate limit check
        if not await self._rate_limit_check():
            logger.warning("Rate limit reached for technographic lookups")
            return self._empty_result()

        # Try BuiltWith API first
        result = await self._fetch_builtwith(domain)

        # Fallback to scraping
        if result is None:
            result = await self._scrape_technologies(domain)

        # Cache the result
        await self._save_cache(domain, result)

        return result

    async def _check_cache(self, domain: str) -> dict[str, Any] | None:
        """Check Redis cache for existing tech stack data."""
        try:
            redis = await self._get_redis()
            key = f"techstack:{domain}"
            data = await redis.get(key)
            if data:
                return json.loads(data)
        except Exception as exc:
            logger.debug("Cache check failed for %s: %s", domain, exc)
        return None

    async def _save_cache(self, domain: str, data: dict[str, Any]) -> None:
        """Save tech stack data to Redis cache."""
        try:
            redis = await self._get_redis()
            key = f"techstack:{domain}"
            await redis.setex(key, _CACHE_TTL, json.dumps(data))
        except Exception as exc:
            logger.debug("Cache save failed for %s: %s", domain, exc)

    async def _rate_limit_check(self) -> bool:
        """Check if rate limit allows another request. Returns True if allowed."""
        try:
            redis = await self._get_redis()
            key = "ratelimit:technographic"
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 60)
            return count <= self._max_requests_per_minute
        except Exception as exc:
            logger.debug("Rate limit check failed: %s", exc)
            return True

    async def _fetch_builtwith(self, domain: str) -> dict[str, Any] | None:
        """Try BuiltWith API. Returns None if API key not set or request fails."""
        if not self._builtwith_api_key:
            return None

        try:
            url = f"https://api.builtwith.com/free1/api.json"
            params = {"KEY": self._builtwith_api_key, "LOOKUP": domain}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        return None
                    data = await response.json()
                    return self._parse_builtwith_response(data)
        except Exception as exc:
            logger.debug("BuiltWith API failed for %s: %s", domain, exc)
            return None

    def _parse_builtwith_response(self, data: dict[str, Any]) -> dict[str, Any]:
        """Parse BuiltWith API response into our structured format."""
        result = self._empty_result()
        groups = data.get("groups", [])
        for group in groups:
            categories = group.get("categories", [])
            for cat in categories:
                tech_name = cat.get("name", "")
                if not tech_name:
                    continue
                # Categorize based on BuiltWith category names
                cat_name_lower = cat.get("name", "").lower()
                if "analytics" in cat_name_lower:
                    result["analytics"].append(tech_name)
                elif "framework" in cat_name_lower or "library" in cat_name_lower:
                    result["frameworks"].append(tech_name)
                elif "cdn" in cat_name_lower:
                    result["cdn"].append(tech_name)
                elif "crm" in cat_name_lower:
                    result["crm"].append(tech_name)
                elif "language" in cat_name_lower:
                    result["languages"].append(tech_name)
                else:
                    result["other"].append(tech_name)
        return result

    async def _scrape_technologies(self, domain: str) -> dict[str, Any]:
        """Fallback: scrape the company website and detect technologies from HTML.

        Checks for:
        - Script src URLs (react, angular, vue, jquery, etc.)
        - Meta tags (generator)
        - Link tags (stylesheets from known CDNs)
        - Common patterns in HTML (Google Analytics IDs, Stripe.js, etc.)
        """
        result = self._empty_result()
        try:
            url = f"https://{domain}"
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; SalesBot/1.0)"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                    allow_redirects=True,
                ) as response:
                    if response.status != 200:
                        return result
                    html = await response.text()
        except Exception as exc:
            logger.debug("Scrape failed for %s: %s", domain, exc)
            return result

        # Detect technologies from HTML content
        detected: set[tuple[str, str]] = set()
        html_lower = html.lower()
        for pattern, (tech_name, category) in TECHNOLOGY_PATTERNS.items():
            if re.search(pattern, html_lower):
                detected.add((tech_name, category))

        for tech_name, category in detected:
            if tech_name not in result[category]:
                result[category].append(tech_name)

        return result

    def _empty_result(self) -> dict[str, Any]:
        """Return empty tech stack structure."""
        return {
            "languages": [],
            "frameworks": [],
            "cdn": [],
            "analytics": [],
            "crm": [],
            "other": [],
        }

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
