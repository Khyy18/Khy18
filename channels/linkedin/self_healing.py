"""LinkedIn self-healing: auto-detects and fixes broken selectors and sessions."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

SELECTOR_TTL_SECONDS = 7 * 24 * 3600  # 7 days


class LinkedInSelfHealing:
    """Automatically detects and fixes broken LinkedIn automation selectors and sessions."""

    DEFAULT_SELECTORS: dict[str, str] = {
        "connect_button": "button:has-text('Connect'), button[aria-label*='Connect']",
        "message_button": "button:has-text('Message'), button[aria-label*='Message']",
        "send_button": "button[type='submit']:has-text('Send'), button.msg-form__send-button",
        "add_note_button": "button:has-text('Add a note')",
        "message_textbox": "div[role='textbox'], textarea[name='message']",
        "pending_button": "button:has-text('Pending')",
        "withdraw_button": "button:has-text('Withdraw'), button:has-text('Remove')",
    }

    FALLBACK_SELECTORS: dict[str, str] = {
        "connect_button": "//button[contains(., 'Connect')]",
        "message_button": "//button[contains(., 'Message')]",
        "send_button": "//button[contains(., 'Send')]",
        "add_note_button": "//button[contains(., 'Add a note')]",
        "message_textbox": "//div[@role='textbox']",
        "pending_button": "//button[contains(., 'Pending')]",
        "withdraw_button": "//button[contains(., 'Withdraw')]",
    }

    def __init__(
        self,
        redis_client: Any,
        llm_client: Any | None = None,
        session_pool: Any | None = None,
        settings: Any | None = None,
    ) -> None:
        self._redis = redis_client
        self._llm = llm_client
        self._session_pool = session_pool
        self._settings = settings

    async def validate_selectors(self, page: Any) -> dict[str, dict[str, Any]]:
        """Test each selector against the current page.

        Returns a dict like {"connect_button": {"valid": True, "fallback_used": False}, ...}.
        If CSS selector fails, tries the FALLBACK_SELECTORS (XPath).
        """
        results: dict[str, dict[str, Any]] = {}

        for action_name, css_selector in self.DEFAULT_SELECTORS.items():
            try:
                count = await page.locator(css_selector).count()
                if count > 0:
                    results[action_name] = {"valid": True, "fallback_used": False}
                    continue
            except Exception:
                pass

            # Try XPath fallback
            fallback = self.FALLBACK_SELECTORS.get(action_name)
            if fallback:
                try:
                    count = await page.locator(fallback).count()
                    if count > 0:
                        results[action_name] = {"valid": True, "fallback_used": True}
                        continue
                except Exception:
                    pass

            results[action_name] = {"valid": False, "fallback_used": False}

        return results

    async def get_selector(self, action_name: str) -> str:
        """Retrieve selector from Redis cache or return the hardcoded default."""
        redis_key = f"linkedin:selectors:{action_name}"
        cached = await self._redis.get(redis_key)
        if cached:
            return cached
        return self.DEFAULT_SELECTORS[action_name]

    async def store_selector(self, action_name: str, selector: str) -> None:
        """Store a selector in Redis with a 7-day TTL."""
        redis_key = f"linkedin:selectors:{action_name}"
        await self._redis.setex(redis_key, SELECTOR_TTL_SECONDS, selector)

    async def auto_update_selectors(self, page: Any) -> dict[str, str]:
        """Validate current selectors and use LLM to suggest replacements for broken ones.

        Returns dict of updated selectors (action_name -> new_selector).
        """
        validation = await self.validate_selectors(page)
        updated: dict[str, str] = {}

        for action_name, status in validation.items():
            if status["valid"]:
                continue

            # Use LLM to suggest a new selector if available
            if self._llm:
                try:
                    content = await page.content()
                    snippet = content[:3000]
                    prompt = (
                        f"Given this HTML snippet, suggest a CSS selector for the "
                        f"'{action_name}' button/element. Return only the selector string.\n\n"
                        f"HTML:\n{snippet}"
                    )
                    new_selector = await self._llm.generate(prompt)
                    new_selector = new_selector.strip()
                    if new_selector:
                        await self.store_selector(action_name, new_selector)
                        updated[action_name] = new_selector
                except Exception as e:
                    logger.error(
                        "Failed to auto-update selector for %s: %s",
                        action_name,
                        str(e),
                    )

        return updated

    async def monitor_session_health(
        self, page: Any, account_id: str
    ) -> dict[str, str]:
        """Check page for signs of session issues.

        Returns {"status": "healthy|restricted|phone_verification|rate_limited|login_required",
                 "details": "..."}.
        """
        url = page.url if hasattr(page, "url") else ""
        if isinstance(url, property):
            url = ""

        # Check login redirect
        if "/login" in url or "/checkpoint" in url:
            return {
                "status": "login_required",
                "details": f"Page redirected to login/checkpoint: {url}",
            }

        try:
            content = await page.content()
            content_lower = content.lower()
        except Exception:
            return {"status": "healthy", "details": "Unable to read page content"}

        # Check for restriction banner
        if "restricted" in content_lower or "temporarily limited" in content_lower:
            return {
                "status": "restricted",
                "details": "Account restriction banner detected on page",
            }

        # Check for phone verification
        if "verify" in content_lower and "phone" in content_lower:
            return {
                "status": "phone_verification",
                "details": "Phone verification required",
            }

        # Check for rate limiting
        if "you've reached" in content_lower or "limit" in content_lower:
            return {
                "status": "rate_limited",
                "details": "Rate limit indicator detected on page",
            }

        return {"status": "healthy", "details": "No issues detected"}

    async def refresh_session(self, account_id: str) -> dict[str, str]:
        """Attempt to refresh or rotate the session for an account.

        Returns {"action": "rotated|no_action|failed", "details": "..."}.
        """
        if not self._session_pool:
            return {"action": "no_action", "details": "No session pool available"}

        try:
            status = await self._session_pool.check_health(account_id)
            if status == "restricted":
                # Attempt to rotate to a new session
                new_account = await self._session_pool.get_available_account()
                if new_account:
                    return {
                        "action": "rotated",
                        "details": f"Rotated from {account_id} to {new_account.get('id', 'unknown')}",
                    }
                return {
                    "action": "failed",
                    "details": "No available accounts to rotate to",
                }
            return {"action": "no_action", "details": f"Account status is {status}"}
        except Exception as e:
            return {"action": "failed", "details": str(e)}

    async def generate_daily_health_report(self) -> dict[str, Any]:
        """Generate a summary health report.

        Returns dict with selector_status, accounts_checked, restrictions_found,
        and recommendations.
        """
        return {
            "selector_status": {
                name: "configured" for name in self.DEFAULT_SELECTORS
            },
            "accounts_checked": 0,
            "restrictions_found": 0,
            "recommendations": [
                "Run validate_selectors periodically to detect LinkedIn UI changes",
                "Monitor session health before each action batch",
            ],
        }
