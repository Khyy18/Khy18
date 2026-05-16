from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from playwright.async_api import Page

logger = logging.getLogger(__name__)

CHALLENGE_URL_PATTERNS = [
    "/checkpoint/",
    "/challenge/",
    "/captcha/",
    "/security/",
    "/authwall",
]


class AntiDetection:
    """Human-like behavior simulation for LinkedIn anti-detection."""

    async def human_type(self, page: Page, selector: str, text: str) -> None:
        """Type text into a selector with random per-character delay (50-150ms)."""
        element = page.locator(selector)
        await element.click()
        for char in text:
            await element.type(char, delay=random.randint(50, 150))
        logger.debug("Typed %d characters into %s", len(text), selector)

    async def random_pause(self, min_s: float = 1.0, max_s: float = 5.0) -> None:
        """Simulate a reading pause with random duration."""
        duration = random.uniform(min_s, max_s)
        await asyncio.sleep(duration)
        logger.debug("Paused for %.2fs", duration)

    async def mouse_move_bezier(self, page: Page, x: float, y: float) -> None:
        """Move mouse along a bezier curve to target coordinates (not teleporting).

        Uses quadratic bezier interpolation with random control point.
        """
        steps = random.randint(15, 30)

        # Get current mouse position (start from center if unknown)
        viewport = page.viewport_size
        start_x = (viewport["width"] // 2) if viewport else 960
        start_y = (viewport["height"] // 2) if viewport else 540

        # Random control point for bezier curve
        ctrl_x = start_x + random.uniform(-100, 100) + (x - start_x) * 0.5
        ctrl_y = start_y + random.uniform(-100, 100) + (y - start_y) * 0.5

        for i in range(1, steps + 1):
            t = i / steps
            # Quadratic bezier: B(t) = (1-t)^2*P0 + 2*(1-t)*t*P1 + t^2*P2
            bx = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * ctrl_x + t ** 2 * x
            by = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * ctrl_y + t ** 2 * y
            await page.mouse.move(bx, by)
            await asyncio.sleep(random.uniform(0.005, 0.02))

        logger.debug("Mouse moved to (%.0f, %.0f) via bezier curve", x, y)

    async def scroll_humanlike(
        self, page: Page, direction: str = "down", amount: int | None = None
    ) -> None:
        """Scroll with variable speed to simulate human scrolling behavior."""
        if amount is None:
            amount = random.randint(200, 600)

        scroll_amount = amount if direction == "down" else -amount

        # Break scroll into smaller increments with variable speed
        remaining = abs(scroll_amount)
        sign = 1 if scroll_amount > 0 else -1

        while remaining > 0:
            chunk = min(remaining, random.randint(50, 150))
            await page.mouse.wheel(0, chunk * sign)
            remaining -= chunk
            await asyncio.sleep(random.uniform(0.05, 0.15))

        logger.debug("Scrolled %s by %dpx", direction, amount)

    async def warm_up_session(self, page: Page) -> None:
        """Warm up session by visiting LinkedIn feed, scrolling, and interacting."""
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(3.0, 6.0))

        # Scroll through feed a few times
        for _ in range(random.randint(2, 4)):
            await self.scroll_humanlike(page, direction="down")
            await self.random_pause(min_s=2.0, max_s=5.0)

        # Try to like a random post (best-effort)
        try:
            like_buttons = page.locator("button[aria-label*='Like']")
            count = await like_buttons.count()
            if count > 0:
                index = random.randint(0, min(count - 1, 3))
                await like_buttons.nth(index).click()
                logger.debug("Liked a post during warm-up")
        except Exception as exc:
            logger.debug("Could not like a post during warm-up: %s", exc)

        await self.random_pause(min_s=1.0, max_s=3.0)
        logger.info("Session warm-up completed")

    async def detect_challenge(self, page: Page) -> bool:
        """Check if LinkedIn has presented a challenge/captcha page."""
        current_url = page.url
        for pattern in CHALLENGE_URL_PATTERNS:
            if pattern in current_url:
                logger.warning("Challenge detected in URL: %s", current_url)
                return True

        # Check page content for challenge indicators
        try:
            content = await page.content()
            challenge_indicators = [
                "Let's do a quick security check",
                "verify your identity",
                "unusual activity",
                "security verification",
            ]
            for indicator in challenge_indicators:
                if indicator.lower() in content.lower():
                    logger.warning("Challenge detected in page content: %s", indicator)
                    return True
        except Exception as exc:
            logger.debug("Error checking for challenge: %s", exc)

        return False

    async def tab_switch_simulation(self, page: Page) -> None:
        """Simulate switching focus away and back to mimic human tab behavior."""
        # Blur the page (simulate switching to another tab)
        await page.evaluate("document.hidden")
        await asyncio.sleep(random.uniform(2.0, 8.0))
        # Refocus
        await page.bring_to_front()
        await asyncio.sleep(random.uniform(0.5, 1.5))
        logger.debug("Tab switch simulation completed")
