"""Enricher Agent - enriches leads with web search and LLM summarization."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import aiohttp

from data.sources.job_boards import JobBoardsClient
from data.sources.technographic import TechnographicClient

if TYPE_CHECKING:
    from core.config import Settings
    from core.llm import LLMClient

logger = logging.getLogger(__name__)

ENRICHMENT_SYSTEM_PROMPT = """You are a sales intelligence analyst. Given search results about a person and their company, extract actionable sales intelligence.

Return your analysis as a structured summary with the following sections:
1. TRIGGER EVENTS: Recent events that create a buying opportunity (funding, expansion, new hire, product launch, partnership)
2. TALKING POINTS: Specific points the sales rep can reference to show they did their research
3. COMPANY NEWS: Notable recent news about the company
4. RECENT ACTIVITY: What the person has been sharing or discussing publicly

Be concise and specific. Focus on information that a sales representative can use to personalize outreach. If no relevant information is found for a section, say "None found"."""

ENRICHMENT_USER_PROMPT = """Research the following lead for sales outreach personalization:

Person: {first_name} {last_name}
Title: {title}
Company: {company}
Industry: {industry}
Company Description: {description}

Here are the web search results I found:

{search_results}

Please analyze these results and provide structured sales intelligence."""


class EnricherAgent:
    """Enriches leads with web-sourced intelligence and LLM analysis."""

    SEARCH_URL = "https://html.duckduckgo.com/html/"

    def __init__(self, llm_client: LLMClient, settings: Settings) -> None:
        self._llm = llm_client
        self._settings = settings

    async def enrich(self, lead: dict[str, Any]) -> dict[str, Any]:
        """Enrich a single lead with web search data and LLM analysis.

        Args:
            lead: Lead dict from researcher with first_name, last_name,
                title, company, company_data, etc.

        Returns:
            Lead dict with added enrichment_data field.
        """
        first_name = lead.get("first_name", "")
        last_name = lead.get("last_name", "")
        company = lead.get("company", "")
        title = lead.get("title", "")

        search_queries = [
            f"{company} news funding announcement",
            f"{first_name} {last_name} {company}",
            f"{company} product launch expansion",
        ]

        # Perform web searches
        search_results: list[str] = []
        async with aiohttp.ClientSession() as session:
            for query in search_queries:
                result = await self._search_web(session, query)
                if result:
                    search_results.append(f"Query: {query}\n{result}")

        combined_results = "\n\n---\n\n".join(search_results) if search_results else "No search results available."

        # Use LLM to analyze search results
        company_data = lead.get("company_data", {})
        user_prompt = ENRICHMENT_USER_PROMPT.format(
            first_name=first_name,
            last_name=last_name,
            title=title,
            company=company,
            industry=company_data.get("industry", "Unknown"),
            description=company_data.get("description", "N/A"),
            search_results=combined_results,
        )

        messages = [
            {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            llm_response = await self._llm.generate(
                messages=messages, temperature=0.3, max_tokens=1024
            )
            enrichment = self._parse_enrichment(llm_response)
        except Exception as exc:
            logger.error(
                "LLM enrichment failed for %s %s: %s",
                first_name,
                last_name,
                exc,
            )
            enrichment = self._empty_enrichment()

        enriched_lead = {**lead}
        enriched_lead["enrichment_data"] = {
            **enrichment,
            "enriched_at": datetime.now(timezone.utc).isoformat(),
        }

        # Enhanced enrichment (technographic + intent signals)
        try:
            redis_url = self._settings.redis_url
            enriched_lead = await self.enrich_technographic(enriched_lead, redis_url)
            enriched_lead = await self.enrich_intent_signals(enriched_lead, redis_url)
        except Exception as exc:
            logger.error(
                "Enhanced enrichment failed for %s %s: %s",
                first_name,
                last_name,
                exc,
            )

        return enriched_lead

    async def enrich_batch(
        self,
        leads: list[dict[str, Any]],
        max_concurrency: int = 5,
    ) -> list[dict[str, Any]]:
        """Enrich multiple leads concurrently.

        Args:
            leads: List of lead dicts to enrich.
            max_concurrency: Maximum concurrent enrichment tasks.

        Returns:
            List of enriched lead dicts.
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _enrich_with_limit(lead: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                try:
                    return await self.enrich(lead)
                except Exception as exc:
                    logger.error(
                        "Enrichment failed for %s: %s",
                        lead.get("email", "unknown"),
                        exc,
                    )
                    enriched = {**lead}
                    enriched["enrichment_data"] = {
                        **self._empty_enrichment(),
                        "enriched_at": datetime.now(timezone.utc).isoformat(),
                    }
                    return enriched

        results = await asyncio.gather(
            *[_enrich_with_limit(lead) for lead in leads]
        )
        return list(results)

    async def _search_web(
        self, session: aiohttp.ClientSession, query: str
    ) -> str:
        """Perform a web search and return summarized results."""
        try:
            params = {"q": query}
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; SalesBot/1.0)"
            }
            async with session.get(
                self.SEARCH_URL,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    return ""
                text = await response.text()
                # Extract snippets from DuckDuckGo HTML response
                return self._extract_snippets(text)
        except Exception as exc:
            logger.debug("Web search failed for '%s': %s", query, exc)
            return ""

    def _extract_snippets(self, html: str) -> str:
        """Extract text snippets from DuckDuckGo HTML results."""
        snippets: list[str] = []
        # Simple extraction of result snippets from HTML
        marker = "result__snippet"
        parts = html.split(marker)
        for part in parts[1:6]:  # Get up to 5 snippets
            # Find the text content after the class marker
            start = part.find(">")
            if start == -1:
                continue
            end = part.find("</", start)
            if end == -1:
                end = min(start + 300, len(part))
            snippet = part[start + 1 : end]
            # Clean HTML tags
            clean = ""
            in_tag = False
            for char in snippet:
                if char == "<":
                    in_tag = True
                elif char == ">":
                    in_tag = False
                elif not in_tag:
                    clean += char
            snippet_text = clean.strip()
            if snippet_text:
                snippets.append(snippet_text)

        return "\n".join(snippets)

    def _parse_enrichment(self, llm_response: str) -> dict[str, Any]:
        """Parse LLM response into structured enrichment data."""
        trigger_events: list[str] = []
        talking_points: list[str] = []
        company_news: list[str] = []
        recent_activity = ""

        current_section = ""
        for line in llm_response.split("\n"):
            line = line.strip()
            if not line:
                continue

            line_upper = line.upper()
            if "TRIGGER EVENT" in line_upper:
                current_section = "trigger_events"
                continue
            elif "TALKING POINT" in line_upper:
                current_section = "talking_points"
                continue
            elif "COMPANY NEWS" in line_upper:
                current_section = "company_news"
                continue
            elif "RECENT ACTIVITY" in line_upper:
                current_section = "recent_activity"
                continue

            # Strip bullet markers
            cleaned = line.lstrip("-*0123456789. ")
            if not cleaned or cleaned.lower() == "none found":
                continue

            if current_section == "trigger_events":
                trigger_events.append(cleaned)
            elif current_section == "talking_points":
                talking_points.append(cleaned)
            elif current_section == "company_news":
                company_news.append(cleaned)
            elif current_section == "recent_activity":
                if recent_activity:
                    recent_activity += " " + cleaned
                else:
                    recent_activity = cleaned

        return {
            "trigger_events": trigger_events,
            "talking_points": talking_points,
            "company_news": company_news,
            "recent_activity": recent_activity,
        }

    def _empty_enrichment(self) -> dict[str, Any]:
        """Return empty enrichment structure."""
        return {
            "trigger_events": [],
            "talking_points": [],
            "company_news": [],
            "recent_activity": "",
        }

    async def enrich_technographic(
        self, lead: dict[str, Any], redis_url: str
    ) -> dict[str, Any]:
        """Add technographic data to lead's enrichment_data.

        Extracts company domain from email or company name.
        Calls TechnographicClient.get_tech_stack().
        Stores result in enrichment_data["tech_stack"].
        """
        domain = self._extract_domain(lead)
        if not domain:
            return lead

        client = TechnographicClient(redis_url=redis_url)
        try:
            tech_stack = await client.get_tech_stack(domain)
            enriched = {**lead}
            enriched["enrichment_data"] = {
                **enriched.get("enrichment_data", {}),
                "tech_stack": tech_stack,
            }
            return enriched
        finally:
            await client.close()

    async def enrich_intent_signals(
        self, lead: dict[str, Any], redis_url: str
    ) -> dict[str, Any]:
        """Add intent signals to lead's enrichment_data.

        Calls JobBoardsClient.search_jobs() for hiring signals.
        Searches web for "{company} funding round" for funding events.

        Stores:
        - enrichment_data["hiring_signals"]: list of relevant job titles
        - enrichment_data["funding_events"]: list of funding-related snippets
        - enrichment_data["intent_score"]: float 0-100
        """
        company = lead.get("company", "")
        if not company:
            return lead

        # Get hiring signals
        client = JobBoardsClient(redis_url=redis_url)
        try:
            job_listings = await client.search_jobs(company)
        finally:
            await client.close()

        # Filter for relevant hiring roles
        relevant_keywords = [
            "sales", "growth", "marketing", "business development",
            "sdr", "bdr", "account executive",
        ]
        hiring_signals = [
            job["title"]
            for job in job_listings
            if any(kw in job["title"].lower() for kw in relevant_keywords)
        ]

        # Search for funding events
        funding_snippets: list[str] = []
        async with aiohttp.ClientSession() as session:
            result = await self._search_web(session, f"{company} funding round")
            if result:
                for line in result.split("\n"):
                    line = line.strip()
                    if line and any(
                        kw in line.lower()
                        for kw in ["funding", "raised", "series", "investment", "round"]
                    ):
                        funding_snippets.append(line)

        # Calculate intent score
        tech_stack = lead.get("enrichment_data", {}).get("tech_stack", {})
        intent_score = self._calculate_intent_score(
            hiring_signals, funding_snippets, tech_stack
        )

        enriched = {**lead}
        enriched["enrichment_data"] = {
            **enriched.get("enrichment_data", {}),
            "hiring_signals": hiring_signals,
            "funding_events": funding_snippets,
            "intent_score": intent_score,
        }
        return enriched

    def _calculate_intent_score(
        self,
        hiring_signals: list[str],
        funding_events: list[str],
        tech_stack: dict[str, Any],
    ) -> float:
        """Calculate intent score from signals.

        Scoring:
        - Hiring for relevant roles: +30
        - Recent funding mentions: +25
        - Tech stack exists and has items: +15
        - Multiple signal categories present: +10 bonus
        """
        score = 0.0
        categories_present = 0

        if hiring_signals:
            score += 30.0
            categories_present += 1

        if funding_events:
            score += 25.0
            categories_present += 1

        # Check if tech_stack has any items
        has_tech = any(
            bool(v) for v in tech_stack.values() if isinstance(v, list)
        )
        if has_tech:
            score += 15.0
            categories_present += 1

        # Compound bonus for multiple signal categories
        if categories_present >= 3:
            score += 10.0

        return min(score, 100.0)

    def _extract_domain(self, lead: dict[str, Any]) -> str:
        """Extract company domain from email or company name."""
        email = lead.get("email", "")
        if email and "@" in email:
            domain = email.split("@")[1]
            # Skip generic email providers
            generic = {
                "gmail.com", "yahoo.com", "hotmail.com",
                "outlook.com", "aol.com", "icloud.com",
            }
            if domain.lower() not in generic:
                return domain

        # Fallback: use company name as a domain guess
        company = lead.get("company", "")
        if company:
            # Simple domain guess: lowercase, remove spaces, add .com
            clean = company.lower().replace(" ", "").replace(",", "")
            return f"{clean}.com"

        return ""
