from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from channels.linkedin.anti_detection import AntiDetection
from channels.linkedin.browser import LinkedInBrowser
from channels.linkedin.session_pool import SessionPool
from compliance.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

MAX_NOTE_LENGTH = 300
MAX_RETRIES = 3


class LinkedInActions:
    """High-level LinkedIn actions with rate limiting, retry logic, and anti-detection."""

    def __init__(
        self,
        browser: LinkedInBrowser,
        anti_detection: AntiDetection,
        session_pool: SessionPool,
        rate_limiter: RateLimiter,
    ) -> None:
        self._browser = browser
        self._anti = anti_detection
        self._pool = session_pool
        self._rate_limiter = rate_limiter

    async def _check_and_handle_challenge(self) -> bool:
        """Check for challenges and pause if detected. Returns True if challenge found."""
        page = self._browser.page
        if await self._anti.detect_challenge(page):
            logger.warning("Challenge detected - pausing all actions")
            await self._browser.screenshot_on_error("challenge_detected")
            return True
        return False

    async def _retry_with_backoff(
        self, action_name: str, coro_factory: Any, account_id: str, action_type: str
    ) -> dict[str, Any]:
        """Execute an action with exponential backoff retry on transient failures."""
        for attempt in range(MAX_RETRIES):
            try:
                # Check for challenge before each attempt
                if await self._check_and_handle_challenge():
                    return {"success": False, "reason": "challenge_detected"}

                result = await coro_factory()

                # Record successful action
                await self._pool.record_action(account_id, action_type)
                return {"success": True, "result": result}

            except Exception as exc:
                wait_time = 2 ** attempt
                logger.warning(
                    "%s attempt %d/%d failed: %s. Retrying in %ds...",
                    action_name,
                    attempt + 1,
                    MAX_RETRIES,
                    str(exc),
                    wait_time,
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(wait_time)

        logger.error("All %d attempts failed for %s", MAX_RETRIES, action_name)
        return {"success": False, "reason": "max_retries_exceeded"}

    async def view_profile(self, url: str) -> dict[str, Any]:
        """View a LinkedIn profile with human-like scrolling and random pauses."""
        account_id = self._browser._account_id

        # Check rate limit
        allowed = await self._rate_limiter.check_rate_limit(
            f"linkedin:rate:{account_id}:profile_view", 50, 86400
        )
        if not allowed:
            return {"success": False, "reason": "rate_limit_exceeded"}

        async def _execute() -> str:
            page = self._browser.page
            await self._browser.navigate(url)
            await self._anti.random_pause(min_s=2.0, max_s=4.0)
            await self._anti.scroll_humanlike(page, direction="down")
            await self._anti.random_pause(min_s=1.0, max_s=3.0)
            await self._anti.scroll_humanlike(page, direction="down")
            await self._anti.random_pause(min_s=1.0, max_s=2.0)
            return page.url

        return await self._retry_with_backoff(
            "view_profile", _execute, account_id, "profile_view"
        )

    async def send_connection_request(
        self, url: str, note: str = ""
    ) -> dict[str, Any]:
        """Visit a profile and send a connection request with optional note."""
        account_id = self._browser._account_id

        # Check rate limit
        allowed = await self._rate_limiter.check_rate_limit(
            f"linkedin:rate:{account_id}:connection_request", 25, 86400
        )
        if not allowed:
            return {"success": False, "reason": "rate_limit_exceeded"}

        # Truncate note to max length
        truncated_note = note[:MAX_NOTE_LENGTH] if note else ""

        async def _execute() -> str:
            page = self._browser.page
            await self._browser.navigate(url)
            await self._anti.random_pause(min_s=2.0, max_s=4.0)

            # Click Connect button
            connect_button = page.locator(
                "button:has-text('Connect'), button[aria-label*='Connect']"
            ).first
            await connect_button.click()
            await self._anti.random_pause(min_s=1.0, max_s=2.0)

            # If note is provided, click "Add a note" and type it
            if truncated_note:
                add_note_button = page.locator("button:has-text('Add a note')")
                if await add_note_button.count() > 0:
                    await add_note_button.click()
                    await self._anti.random_pause(min_s=0.5, max_s=1.5)
                    await self._anti.human_type(
                        page, "textarea[name='message']", truncated_note
                    )
                    await self._anti.random_pause(min_s=0.5, max_s=1.0)

            # Click Send
            send_button = page.locator(
                "button:has-text('Send'), button[aria-label='Send now']"
            ).first
            await send_button.click()
            await self._anti.random_pause(min_s=1.0, max_s=2.0)

            logger.info("Connection request sent to %s", url)
            return "connection_request_sent"

        return await self._retry_with_backoff(
            "send_connection_request", _execute, account_id, "connection_request"
        )

    async def send_message(self, url: str, text: str) -> dict[str, Any]:
        """Send a message to a 1st-degree connection."""
        account_id = self._browser._account_id

        # Check rate limit
        allowed = await self._rate_limiter.check_rate_limit(
            f"linkedin:rate:{account_id}:message", 20, 86400
        )
        if not allowed:
            return {"success": False, "reason": "rate_limit_exceeded"}

        async def _execute() -> str:
            page = self._browser.page
            await self._browser.navigate(url)
            await self._anti.random_pause(min_s=2.0, max_s=4.0)

            # Click Message button
            message_button = page.locator(
                "button:has-text('Message'), button[aria-label*='Message']"
            ).first
            await message_button.click()
            await self._anti.random_pause(min_s=1.0, max_s=2.0)

            # Type the message
            message_box = page.locator(
                "div[role='textbox'], textarea[name='message']"
            ).first
            await message_box.click()
            for char in text:
                await message_box.type(char, delay=random.randint(50, 150))
            await self._anti.random_pause(min_s=0.5, max_s=1.5)

            # Send the message
            send_button = page.locator(
                "button[type='submit']:has-text('Send'), button.msg-form__send-button"
            ).first
            await send_button.click()
            await self._anti.random_pause(min_s=1.0, max_s=2.0)

            logger.info("Message sent to %s", url)
            return "message_sent"

        return await self._retry_with_backoff(
            "send_message", _execute, account_id, "message"
        )

    async def check_connection_status(self, url: str) -> dict[str, Any]:
        """Check the connection status by visiting a profile and reading the action button."""
        account_id = self._browser._account_id

        async def _execute() -> str:
            page = self._browser.page
            await self._browser.navigate(url)
            await self._anti.random_pause(min_s=2.0, max_s=3.0)

            # Check for different button states
            if await page.locator("button:has-text('Message')").count() > 0:
                return "connected"
            elif await page.locator("button:has-text('Pending')").count() > 0:
                return "pending"
            elif await page.locator("button:has-text('Connect')").count() > 0:
                return "not_connected"
            elif await page.locator("button:has-text('Follow')").count() > 0:
                return "not_connected"
            else:
                return "unknown"

        try:
            result = await _execute()
            return {"success": True, "status": result}
        except Exception as exc:
            logger.error("Failed to check connection status for %s: %s", url, exc)
            return {"success": False, "reason": str(exc)}

    async def withdraw_pending_request(self, url: str) -> dict[str, Any]:
        """Withdraw a pending connection invitation."""
        account_id = self._browser._account_id

        async def _execute() -> str:
            page = self._browser.page
            await self._browser.navigate(url)
            await self._anti.random_pause(min_s=2.0, max_s=3.0)

            # Click Pending button to get withdraw option
            pending_button = page.locator("button:has-text('Pending')").first
            await pending_button.click()
            await self._anti.random_pause(min_s=0.5, max_s=1.5)

            # Click Withdraw
            withdraw_button = page.locator(
                "button:has-text('Withdraw'), button:has-text('Remove')"
            ).first
            await withdraw_button.click()
            await self._anti.random_pause(min_s=1.0, max_s=2.0)

            logger.info("Pending request withdrawn for %s", url)
            return "request_withdrawn"

        try:
            result = await _execute()
            return {"success": True, "result": result}
        except Exception as exc:
            logger.error("Failed to withdraw request for %s: %s", url, exc)
            return {"success": False, "reason": str(exc)}

    async def accept_connection(self, url: str) -> dict[str, Any]:
        """Accept an incoming connection request."""
        account_id = self._browser._account_id

        async def _execute() -> str:
            page = self._browser.page
            await self._browser.navigate(url)
            await self._anti.random_pause(min_s=2.0, max_s=3.0)

            # Click Accept button
            accept_button = page.locator(
                "button:has-text('Accept'), button[aria-label*='Accept']"
            ).first
            await accept_button.click()
            await self._anti.random_pause(min_s=1.0, max_s=2.0)

            logger.info("Connection accepted for %s", url)
            return "connection_accepted"

        try:
            result = await _execute()
            return {"success": True, "result": result}
        except Exception as exc:
            logger.error("Failed to accept connection for %s: %s", url, exc)
            return {"success": False, "reason": str(exc)}
