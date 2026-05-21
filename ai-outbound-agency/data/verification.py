from typing import Any

from data.sources.hunter import HunterClient


class EmailVerifier:
    """Email verification orchestrator using Hunter.io with batch support and caching."""

    def __init__(self, hunter_client: HunterClient) -> None:
        self._hunter = hunter_client
        self._cache: dict[str, dict[str, Any]] = {}

    async def verify_email(self, email: str) -> dict[str, Any]:
        """Verify a single email address with caching.

        Args:
            email: Email address to verify.

        Returns:
            Verification result from Hunter.io.
        """
        if email in self._cache:
            return self._cache[email]

        result = await self._hunter.verify_email(email)
        self._cache[email] = result
        return result

    async def verify_batch(self, emails: list[str]) -> dict[str, dict[str, Any]]:
        """Verify a batch of email addresses.

        Args:
            emails: List of email addresses to verify.

        Returns:
            Dict mapping email to verification result.
        """
        results: dict[str, dict[str, Any]] = {}

        for email in emails:
            results[email] = await self.verify_email(email)

        return results

    def is_deliverable(self, result: dict[str, Any]) -> bool:
        """Check if verification result indicates the email is deliverable."""
        return result.get("status") == "valid" or result.get("result") == "deliverable"

    def clear_cache(self) -> None:
        """Clear the verification cache."""
        self._cache.clear()
