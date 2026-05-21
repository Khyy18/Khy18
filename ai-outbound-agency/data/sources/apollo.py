from typing import Any

import httpx


class ApolloClient:
    """Apollo.io API client for people and company search."""

    BASE_URL = "https://api.apollo.io/v1"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=30.0,
            headers={"Content-Type": "application/json"},
        )

    async def search_people(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """Search for people by title, company, location, etc.

        Args:
            query: Search parameters (person_titles, organization_domains,
                   person_locations, etc.)

        Returns:
            List of people matching the search criteria.
        """
        results: list[dict[str, Any]] = []
        page = 1

        while True:
            payload = {
                "api_key": self._api_key,
                "page": page,
                "per_page": 100,
                **query,
            }
            response = await self._client.post(
                "/mixed_people/search", json=payload
            )
            response.raise_for_status()
            data = response.json()

            people = data.get("people", [])
            if not people:
                break

            results.extend(people)

            pagination = data.get("pagination", {})
            total_pages = pagination.get("total_pages", 1)
            if page >= total_pages:
                break
            page += 1

        return results

    async def search_companies(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """Search for companies by industry, size, location, etc.

        Args:
            query: Search parameters (organization_industry_tag_ids,
                   organization_num_employees_ranges, etc.)

        Returns:
            List of companies matching the search criteria.
        """
        results: list[dict[str, Any]] = []
        page = 1

        while True:
            payload = {
                "api_key": self._api_key,
                "page": page,
                "per_page": 100,
                **query,
            }
            response = await self._client.post(
                "/mixed_companies/search", json=payload
            )
            response.raise_for_status()
            data = response.json()

            companies = data.get("organizations", [])
            if not companies:
                break

            results.extend(companies)

            pagination = data.get("pagination", {})
            total_pages = pagination.get("total_pages", 1)
            if page >= total_pages:
                break
            page += 1

        return results

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
