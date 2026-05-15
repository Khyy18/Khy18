"""LinkedIn worker tasks for ARQ queue."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def linkedin_connect_task(
    ctx: dict[str, Any],
    profile_url: str,
    tenant_id: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Send a LinkedIn connection request via LinkedInActions."""
    from channels.linkedin.actions import LinkedInActions
    from channels.linkedin.browser import LinkedInBrowser
    from channels.linkedin.anti_detection import AntiDetection
    from channels.linkedin.session_pool import SessionPool
    from compliance.rate_limiter import RateLimiter

    browser = LinkedInBrowser()
    anti_detection = AntiDetection()
    session_pool = SessionPool()
    rate_limiter = RateLimiter()

    actions = LinkedInActions(
        browser=browser,
        anti_detection=anti_detection,
        session_pool=session_pool,
        rate_limiter=rate_limiter,
        tenant_id=tenant_id,
    )
    result = await actions.send_connection_request(profile_url, note=note or "")
    logger.info("LinkedIn connect task completed for %s: %s", profile_url, result)
    return result


async def linkedin_message_task(
    ctx: dict[str, Any],
    profile_url: str,
    tenant_id: str,
    message: str,
) -> dict[str, Any]:
    """Send a LinkedIn message via LinkedInActions."""
    from channels.linkedin.actions import LinkedInActions
    from channels.linkedin.browser import LinkedInBrowser
    from channels.linkedin.anti_detection import AntiDetection
    from channels.linkedin.session_pool import SessionPool
    from compliance.rate_limiter import RateLimiter

    browser = LinkedInBrowser()
    anti_detection = AntiDetection()
    session_pool = SessionPool()
    rate_limiter = RateLimiter()

    actions = LinkedInActions(
        browser=browser,
        anti_detection=anti_detection,
        session_pool=session_pool,
        rate_limiter=rate_limiter,
        tenant_id=tenant_id,
    )
    result = await actions.send_message(profile_url, message)
    logger.info("LinkedIn message task completed for %s: %s", profile_url, result)
    return result


async def linkedin_view_task(
    ctx: dict[str, Any],
    profile_url: str,
    tenant_id: str,
) -> dict[str, Any]:
    """View a LinkedIn profile via LinkedInActions."""
    from channels.linkedin.actions import LinkedInActions
    from channels.linkedin.browser import LinkedInBrowser
    from channels.linkedin.anti_detection import AntiDetection
    from channels.linkedin.session_pool import SessionPool
    from compliance.rate_limiter import RateLimiter

    browser = LinkedInBrowser()
    anti_detection = AntiDetection()
    session_pool = SessionPool()
    rate_limiter = RateLimiter()

    actions = LinkedInActions(
        browser=browser,
        anti_detection=anti_detection,
        session_pool=session_pool,
        rate_limiter=rate_limiter,
        tenant_id=tenant_id,
    )
    result = await actions.view_profile(profile_url)
    logger.info("LinkedIn view task completed for %s: %s", profile_url, result)
    return result
