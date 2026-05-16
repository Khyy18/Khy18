from __future__ import annotations

import asyncio
import logging
import os
import random
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
]

LANGUAGES = ["en-US", "en-GB", "en"]


class LinkedInBrowser:
    """Playwright-based browser automation for LinkedIn with fingerprint randomization."""

    def __init__(
        self,
        session_dir: str,
        proxy: dict[str, str] | None = None,
        account_id: str = "default",
    ) -> None:
        self._session_dir = session_dir
        self._proxy = proxy
        self._account_id = account_id
        self._playwright: Any = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> "LinkedInBrowser":
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()

    @property
    def page(self) -> Page:
        """Return the active page."""
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    async def start(self) -> None:
        """Launch Chromium with persistent context, fingerprint randomization, and optional proxy."""
        user_data_dir = os.path.join(self._session_dir, self._account_id)
        Path(user_data_dir).mkdir(parents=True, exist_ok=True)

        self._playwright = await async_playwright().start()

        viewport_width = random.randint(1280, 1920)
        viewport_height = random.randint(720, 1080)
        user_agent = random.choice(USER_AGENTS)
        timezone_id = random.choice(TIMEZONES)
        locale = random.choice(LANGUAGES)

        launch_options: dict[str, Any] = {
            "user_data_dir": user_data_dir,
            "headless": True,
            "viewport": {"width": viewport_width, "height": viewport_height},
            "user_agent": user_agent,
            "timezone_id": timezone_id,
            "locale": locale,
            "ignore_https_errors": True,
        }

        if self._proxy:
            launch_options["proxy"] = self._proxy

        self._context = await self._playwright.chromium.launch_persistent_context(
            **launch_options
        )

        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()

        logger.info(
            "Browser started for account %s (viewport=%dx%d, ua=%s)",
            self._account_id,
            viewport_width,
            viewport_height,
            user_agent[:50],
        )

    async def stop(self) -> None:
        """Save cookies and close browser context."""
        if self._context:
            try:
                await self._context.close()
            except Exception as exc:
                logger.warning("Error closing browser context: %s", exc)
            self._context = None
            self._page = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        logger.info("Browser stopped for account %s", self._account_id)

    async def navigate(self, url: str) -> None:
        """Navigate to URL with a human-like random delay."""
        page = self.page
        delay = random.uniform(2.0, 8.0)
        await asyncio.sleep(delay)
        await page.goto(url, wait_until="domcontentloaded")
        logger.debug("Navigated to %s (delay=%.1fs)", url, delay)

    async def screenshot_on_error(self, name: str) -> None:
        """Save a debug screenshot for error analysis."""
        page = self.page
        screenshot_dir = os.path.join(self._session_dir, "screenshots")
        Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
        path = os.path.join(screenshot_dir, f"{name}.png")
        try:
            await page.screenshot(path=path)
            logger.info("Screenshot saved: %s", path)
        except Exception as exc:
            logger.warning("Failed to save screenshot %s: %s", name, exc)

    def _random_delay(self, min_s: float = 1.0, max_s: float = 3.0) -> float:
        """Generate a random delay value between min and max seconds."""
        return random.uniform(min_s, max_s)
