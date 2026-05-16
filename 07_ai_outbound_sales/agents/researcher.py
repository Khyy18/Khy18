"""Research Agent - finds and scores leads based on ICP criteria."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.config import Settings
    from data.sources.apollo import ApolloClient

logger = logging.getLogger(__name__)


class ResearcherAgent:
    """Finds potential leads from Apollo.io based on Ideal Customer Profile criteria."""

    def __init__(self, apollo_client: ApolloClient, settings: Settings) -> None:
        self._apollo = apollo_client
        self._settings = settings

    async def research(
        self,
        icp_criteria: dict[str, Any],
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Search for leads matching ICP criteria.

        Args:
            icp_criteria: Dict with keys: industry, company_size_min,
                company_size_max, titles (list), locations (list), keywords (list).
            max_results: Maximum number of leads to return.

        Returns:
            Scored and sorted list of lead dicts.
        """
        industry: str = icp_criteria.get("industry", "")
        company_size_min: int = icp_criteria.get("company_size_min", 1)
        company_size_max: int = icp_criteria.get("company_size_max", 10000)
        titles: list[str] = icp_criteria.get("titles", [])
        locations: list[str] = icp_criteria.get("locations", [])
        keywords: list[str] = icp_criteria.get("keywords", [])

        size_range = f"{company_size_min},{company_size_max}"

        # Step 1: Search for companies matching criteria
        company_query: dict[str, Any] = {
            "organization_num_employees_ranges": [size_range],
        }
        if industry:
            company_query["organization_industry_tag_ids"] = [industry]
        if locations:
            company_query["organization_locations"] = locations
        if keywords:
            company_query["q_organization_keyword_tags"] = keywords

        logger.info("Searching companies with criteria: %s", company_query)

        try:
            companies = await self._apollo.search_companies(company_query)
        except Exception as exc:
            logger.error("Company search failed: %s", exc)
            return []

        if not companies:
            logger.warning("No companies found for criteria")
            return []

        logger.info("Found %d companies, searching for people", len(companies))

        # Step 2: For each company, search people matching title filters
        leads: list[dict[str, Any]] = []
        semaphore = asyncio.Semaphore(5)

        async def _search_people_at_company(
            company: dict[str, Any],
        ) -> list[dict[str, Any]]:
            async with semaphore:
                domain = company.get("primary_domain") or company.get("domain", "")
                if not domain:
                    return []

                people_query: dict[str, Any] = {
                    "organization_domains": [domain],
                }
                if titles:
                    people_query["person_titles"] = titles
                if locations:
                    people_query["person_locations"] = locations

                try:
                    people = await self._apollo.search_people(people_query)
                except Exception as exc:
                    logger.warning(
                        "People search failed for %s: %s", domain, exc
                    )
                    return []

                results: list[dict[str, Any]] = []
                for person in people:
                    lead = self._build_lead(person, company, icp_criteria)
                    if lead:
                        results.append(lead)
                return results

        tasks = [
            _search_people_at_company(company) for company in companies[:20]
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.warning("People search task failed: %s", result)
                continue
            leads.extend(result)

        # Step 3: Score and sort leads
        scored_leads = [self._score_lead(lead, icp_criteria) for lead in leads]
        scored_leads.sort(key=lambda x: x["score"], reverse=True)

        final_results = scored_leads[:max_results]
        logger.info(
            "Research complete: %d leads found, returning top %d",
            len(scored_leads),
            len(final_results),
        )
        return final_results

    def _build_lead(
        self,
        person: dict[str, Any],
        company: dict[str, Any],
        icp_criteria: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Build a structured lead dict from Apollo person and company data."""
        email = person.get("email")
        if not email:
            return None

        return {
            "first_name": person.get("first_name", ""),
            "last_name": person.get("last_name", ""),
            "email": email,
            "title": person.get("title", ""),
            "company": company.get("name", ""),
            "linkedin_url": person.get("linkedin_url", ""),
            "score": 0.0,
            "company_data": {
                "name": company.get("name", ""),
                "domain": company.get("primary_domain", ""),
                "industry": company.get("industry", ""),
                "employee_count": company.get("estimated_num_employees", 0),
                "description": company.get("short_description", ""),
                "location": company.get("city", ""),
                "founded_year": company.get("founded_year"),
                "annual_revenue": company.get("annual_revenue"),
            },
        }

    def _score_lead(
        self, lead: dict[str, Any], icp_criteria: dict[str, Any]
    ) -> dict[str, Any]:
        """Score a lead based on how well it matches the ICP criteria."""
        score = 0.0
        titles: list[str] = icp_criteria.get("titles", [])
        locations: list[str] = icp_criteria.get("locations", [])
        company_size_min: int = icp_criteria.get("company_size_min", 1)
        company_size_max: int = icp_criteria.get("company_size_max", 10000)

        lead_title = lead.get("title", "").lower()
        for target_title in titles:
            if target_title.lower() in lead_title:
                score += 30.0
                break

        employee_count = lead.get("company_data", {}).get("employee_count", 0)
        if company_size_min <= employee_count <= company_size_max:
            score += 25.0
        elif employee_count > 0:
            score += 10.0

        lead_location = lead.get("company_data", {}).get("location", "").lower()
        for target_location in locations:
            if target_location.lower() in lead_location:
                score += 20.0
                break

        if lead.get("email"):
            score += 15.0
        if lead.get("linkedin_url"):
            score += 10.0

        lead["score"] = round(score, 2)
        return lead
