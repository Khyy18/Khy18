from __future__ import annotations
from typing import Any

import httpx


class HunterClient:
    """Hunter.io API client for email verification."""

    BASE_URL = "https://api.hunter.io/v2"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=30.0,
        )

    async def verify_email(self, email: str) -> dict[str, Any]:
        """Verify an email address.

        Args:
            email: Email address to verify.

        Returns:
            Verification result dict with keys: status (deliverable/risky/undeliverable),
            score, result, and additional details.
        """
        response = await self._client.get(
            "/email-verifier",
            params={"email": email, "api_key": self._api_key},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data", {})

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
