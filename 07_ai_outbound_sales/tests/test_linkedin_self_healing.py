"""Tests for LinkedIn self-healing module."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from channels.linkedin.self_healing import LinkedInSelfHealing


@pytest.fixture
def self_healing(mock_redis):
    """Create a LinkedInSelfHealing instance with mock dependencies."""
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="button.new-selector")
    session_pool = AsyncMock()
    session_pool.check_health = AsyncMock(return_value="active")
    session_pool.get_available_account = AsyncMock(return_value={"id": "acc2"})
    return LinkedInSelfHealing(
        redis_client=mock_redis,
        llm_client=llm,
        session_pool=session_pool,
    )


def _make_page_mock(selector_counts: dict[str, int] | None = None, url: str = "https://linkedin.com/feed", content: str = "<html></html>"):
    """Create a mock page object with configurable locator counts."""
    page = MagicMock()
    page.url = url

    default_count = 1 if selector_counts is None else 0

    def locator_side_effect(selector: str):
        loc = AsyncMock()
        if selector_counts is not None:
            count_val = selector_counts.get(selector, default_count)
        else:
            count_val = default_count
        loc.count = AsyncMock(return_value=count_val)
        return loc

    page.locator = MagicMock(side_effect=locator_side_effect)
    page.content = AsyncMock(return_value=content)
    return page


@pytest.mark.asyncio
async def test_validate_selectors_all_valid(self_healing):
    """All CSS selectors match elements on page."""
    page = _make_page_mock()  # All selectors return count=1 by default

    result = await self_healing.validate_selectors(page)

    assert len(result) == len(LinkedInSelfHealing.DEFAULT_SELECTORS)
    for action_name, status in result.items():
        assert status["valid"] is True
        assert status["fallback_used"] is False


@pytest.mark.asyncio
async def test_validate_selectors_with_fallback(self_healing):
    """CSS selector fails but XPath fallback works."""
    # CSS selectors return 0, XPath selectors return 1
    css_selectors = set(LinkedInSelfHealing.DEFAULT_SELECTORS.values())
    fallback_selectors = set(LinkedInSelfHealing.FALLBACK_SELECTORS.values())

    def locator_side_effect(selector: str):
        loc = AsyncMock()
        if selector in css_selectors:
            loc.count = AsyncMock(return_value=0)
        elif selector in fallback_selectors:
            loc.count = AsyncMock(return_value=1)
        else:
            loc.count = AsyncMock(return_value=0)
        return loc

    page = MagicMock()
    page.url = "https://linkedin.com/feed"
    page.locator = MagicMock(side_effect=locator_side_effect)
    page.content = AsyncMock(return_value="<html></html>")

    result = await self_healing.validate_selectors(page)

    for action_name, status in result.items():
        assert status["valid"] is True
        assert status["fallback_used"] is True


@pytest.mark.asyncio
async def test_get_selector_from_redis(self_healing, mock_redis):
    """get_selector returns cached Redis value when available."""
    mock_redis._store["linkedin:selectors:connect_button"] = "button.cached-selector"

    result = await self_healing.get_selector("connect_button")

    assert result == "button.cached-selector"


@pytest.mark.asyncio
async def test_get_selector_default(self_healing, mock_redis):
    """get_selector returns DEFAULT_SELECTORS when no Redis value exists."""
    result = await self_healing.get_selector("connect_button")

    assert result == LinkedInSelfHealing.DEFAULT_SELECTORS["connect_button"]


@pytest.mark.asyncio
async def test_store_selector(self_healing, mock_redis):
    """store_selector persists the selector in Redis."""
    await self_healing.store_selector("connect_button", "button.new")

    assert mock_redis._store["linkedin:selectors:connect_button"] == "button.new"


@pytest.mark.asyncio
async def test_monitor_session_healthy(self_healing):
    """Healthy page returns status='healthy'."""
    page = _make_page_mock(content="<html><body>Normal LinkedIn Feed</body></html>")

    result = await self_healing.monitor_session_health(page, "acc1")

    assert result["status"] == "healthy"


@pytest.mark.asyncio
async def test_monitor_session_restricted(self_healing):
    """Page with restriction banner returns status='restricted'."""
    page = _make_page_mock(
        content="<html><body>Your account has been restricted temporarily.</body></html>"
    )

    result = await self_healing.monitor_session_health(page, "acc1")

    assert result["status"] == "restricted"


@pytest.mark.asyncio
async def test_monitor_session_login_required(self_healing):
    """Page URL with /login returns status='login_required'."""
    page = _make_page_mock(url="https://www.linkedin.com/login")

    result = await self_healing.monitor_session_health(page, "acc1")

    assert result["status"] == "login_required"


@pytest.mark.asyncio
async def test_monitor_session_phone_verification(self_healing):
    """Page with phone verification prompt returns status='phone_verification'."""
    page = _make_page_mock(
        content="<html><body>Please verify your phone number to continue.</body></html>"
    )

    result = await self_healing.monitor_session_health(page, "acc1")

    assert result["status"] == "phone_verification"


@pytest.mark.asyncio
async def test_daily_health_report_structure(self_healing):
    """Health report contains expected keys."""
    report = await self_healing.generate_daily_health_report()

    assert "selector_status" in report
    assert "accounts_checked" in report
    assert "restrictions_found" in report
    assert "recommendations" in report
    assert isinstance(report["recommendations"], list)


@pytest.mark.asyncio
async def test_auto_update_selectors_uses_llm(self_healing):
    """auto_update_selectors calls LLM for broken selectors and stores result."""
    # All CSS and XPath selectors fail
    def locator_side_effect(selector: str):
        loc = AsyncMock()
        loc.count = AsyncMock(return_value=0)
        return loc

    page = MagicMock()
    page.url = "https://linkedin.com/feed"
    page.locator = MagicMock(side_effect=locator_side_effect)
    page.content = AsyncMock(return_value="<html><body>page content</body></html>")

    updated = await self_healing.auto_update_selectors(page)

    # All selectors should be updated via LLM
    assert len(updated) == len(LinkedInSelfHealing.DEFAULT_SELECTORS)
    for action_name in LinkedInSelfHealing.DEFAULT_SELECTORS:
        assert action_name in updated
        assert updated[action_name] == "button.new-selector"


@pytest.mark.asyncio
async def test_refresh_session_rotates_on_restricted(self_healing):
    """refresh_session rotates to new account when current is restricted."""
    self_healing._session_pool.check_health = AsyncMock(return_value="restricted")

    result = await self_healing.refresh_session("acc1")

    assert result["action"] == "rotated"
    assert "acc2" in result["details"]


@pytest.mark.asyncio
async def test_refresh_session_no_action_when_healthy(self_healing):
    """refresh_session takes no action when account is healthy."""
    self_healing._session_pool.check_health = AsyncMock(return_value="active")

    result = await self_healing.refresh_session("acc1")

    assert result["action"] == "no_action"
