"""Tests for competitive intelligence agent and scheduler."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from agents.competitive_intel import CompetitiveIntelAgent
from scheduler.competitive_intel_scheduler import CompetitiveIntelScheduler
from core.models import CompetitiveIntel

from sqlalchemy import select


@pytest.fixture
def intel_agent(session_factory, mock_redis):
    """Create a CompetitiveIntelAgent with mock dependencies."""
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="Pricing summary: Basic $29, Pro $99")
    return CompetitiveIntelAgent(
        session_factory=session_factory,
        llm_client=llm,
        settings=None,
        redis_client=mock_redis,
    )


@pytest.fixture
def intel_scheduler(session_factory, mock_redis):
    """Create a CompetitiveIntelScheduler with mock dependencies."""
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="Summary text")
    return CompetitiveIntelScheduler(
        session_factory=session_factory,
        llm_client=llm,
        settings=None,
        redis_client=mock_redis,
    )


@pytest.mark.asyncio
async def test_scrape_pricing_stores_record(intel_agent, session_factory):
    """scrape_pricing stores a CompetitiveIntel record with category='pricing'."""
    with patch("agents.competitive_intel.httpx.AsyncClient") as mock_client_cls:
        mock_response = MagicMock()
        mock_response.text = "<html><body>Basic: $29/mo, Pro: $99/mo</body></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await intel_agent.scrape_pricing("Instantly.ai", "https://instantly.ai/pricing")

    assert result["success"] is True

    # Verify record was stored
    async with session_factory() as session:
        stmt = select(CompetitiveIntel).where(CompetitiveIntel.category == "pricing")
        db_result = await session.execute(stmt)
        records = db_result.scalars().all()
        assert len(records) == 1
        assert records[0].competitor_name == "Instantly.ai"
        assert records[0].source == "https://instantly.ai/pricing"


@pytest.mark.asyncio
async def test_scrape_pricing_handles_error(intel_agent):
    """scrape_pricing returns success=False when HTTP request fails."""
    with patch("agents.competitive_intel.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx_error())
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await intel_agent.scrape_pricing("Instantly.ai", "https://instantly.ai/pricing")

    assert result["success"] is False
    assert "error" in result


@pytest.mark.asyncio
async def test_cache_prevents_rescrape(intel_agent, mock_redis):
    """_is_cached returns True after _mark_cached, preventing re-scrape."""
    url = "https://instantly.ai/pricing"

    # Initially not cached
    assert await intel_agent._is_cached(url) is False

    # Mark as cached
    await intel_agent._mark_cached(url)

    # Now cached
    assert await intel_agent._is_cached(url) is True


@pytest.mark.asyncio
async def test_weekly_tick_respects_cache(intel_scheduler, mock_redis):
    """run_weekly_tick skips cached competitors and scrapes uncached ones."""
    # Cache the first competitor's pricing URL
    first_pricing_url = CompetitiveIntelAgent.DEFAULT_COMPETITORS[0]["pricing_url"]
    first_changelog_url = CompetitiveIntelAgent.DEFAULT_COMPETITORS[0]["changelog_url"]
    await intel_scheduler._agent._mark_cached(first_pricing_url)
    await intel_scheduler._agent._mark_cached(first_changelog_url)

    with patch("agents.competitive_intel.httpx.AsyncClient") as mock_client_cls:
        mock_response = MagicMock()
        mock_response.text = "<html><body>Content</body></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await intel_scheduler.run_weekly_tick()

    assert result["competitors_checked"] == 3
    assert result["cached_skipped"] == 2  # First competitor's pricing + changelog
    # Other 2 competitors x 2 URLs = 4 scraped
    assert result["scraped"] == 4


@pytest.mark.asyncio
async def test_generate_weekly_digest(intel_agent, session_factory):
    """generate_weekly_digest returns entries from last 7 days."""
    # Create some test records
    async with session_factory() as session:
        for i in range(3):
            record = CompetitiveIntel(
                source=f"https://example.com/{i}",
                category="pricing",
                content=f"Content {i}",
                summary=f"Summary {i}",
                competitor_name=f"Competitor {i}",
            )
            session.add(record)
        await session.commit()

    # Generate digest
    async with session_factory() as session:
        result = await intel_agent.generate_weekly_digest(session)

    assert result["entries_count"] == 3
    assert "digest" in result
    assert len(result["digest"]) > 0


@pytest.mark.asyncio
async def test_brand_mention_placeholder(intel_agent, session_factory):
    """check_brand_mentions stores record and returns success."""
    result = await intel_agent.check_brand_mentions("OurBrand")

    assert result["success"] is True
    assert result["brand_name"] == "OurBrand"

    # Verify DB record
    async with session_factory() as session:
        stmt = select(CompetitiveIntel).where(
            CompetitiveIntel.category == "brand_mention"
        )
        db_result = await session.execute(stmt)
        records = db_result.scalars().all()
        assert len(records) == 1
        assert records[0].competitor_name == "OurBrand"


@pytest.mark.asyncio
async def test_monitor_sentiment_placeholder(intel_agent, session_factory):
    """monitor_sentiment stores record and returns expected structure."""
    result = await intel_agent.monitor_sentiment("reddit")

    assert result["success"] is True
    assert result["source"] == "reddit"
    assert "placeholder" in result["note"].lower()

    # Verify DB record
    async with session_factory() as session:
        stmt = select(CompetitiveIntel).where(
            CompetitiveIntel.category == "sentiment"
        )
        db_result = await session.execute(stmt)
        records = db_result.scalars().all()
        assert len(records) == 1


@pytest.mark.asyncio
async def test_scrape_changelog_stores_record(intel_agent, session_factory):
    """scrape_changelog stores a CompetitiveIntel record with category='features'."""
    with patch("agents.competitive_intel.httpx.AsyncClient") as mock_client_cls:
        mock_response = MagicMock()
        mock_response.text = "<html><body>New feature: AI email warmup</body></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await intel_agent.scrape_changelog("Apollo.io", "https://apollo.io/blog")

    assert result["success"] is True

    async with session_factory() as session:
        stmt = select(CompetitiveIntel).where(CompetitiveIntel.category == "features")
        db_result = await session.execute(stmt)
        records = db_result.scalars().all()
        assert len(records) == 1
        assert records[0].competitor_name == "Apollo.io"


def httpx_error():
    """Create an httpx connection error for testing."""
    import httpx
    return httpx.ConnectError("Connection refused")
