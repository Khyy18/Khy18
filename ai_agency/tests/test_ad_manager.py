"""Tests for ad_manager module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import ad_manager
import database


@pytest.mark.asyncio
class TestAdManager:
    """Tests for ad automation module."""

    async def test_calculate_ad_budget_no_revenue(self, initialized_db):
        """calculate_ad_budget returns 0 when no revenue."""
        budget = await ad_manager.calculate_ad_budget(7)
        assert budget == 0.0

    async def test_calculate_ad_budget_with_revenue(self, initialized_db):
        """calculate_ad_budget returns AD_BUDGET_PERCENT% of revenue."""
        import config
        await database.get_or_create_client(telegram_id=300, username="adclient")
        order_id = await database.create_order(
            client_id=300, service_type="rewrite", input_text="test", price=1000.0
        )
        await database.update_order_status(order_id, "completed", output_text="result")

        budget = await ad_manager.calculate_ad_budget(7)
        expected = 1000.0 * config.AD_BUDGET_PERCENT / 100
        assert budget == expected

    async def test_recommend_channels_low_budget(self, initialized_db):
        """recommend_channels returns empty for very low budget."""
        recs = await ad_manager.recommend_channels("copywriting", 100)
        assert recs == []

    async def test_recommend_channels_sufficient_budget(self, initialized_db):
        """recommend_channels returns recommendations for sufficient budget."""
        recs = await ad_manager.recommend_channels("copywriting", 2000)
        assert len(recs) >= 1
        assert recs[0]["topic"] == "copywriting"
        assert recs[0]["subscribers"] > 0

    async def test_create_ad_campaign(self, initialized_db):
        """create_ad_campaign creates a campaign record."""
        campaign_id = await ad_manager.create_ad_campaign("@test_channel", 5000.0)
        assert campaign_id is not None
        assert campaign_id > 0

    async def test_get_ad_stats(self, initialized_db):
        """get_ad_stats returns summary dict."""
        await ad_manager.create_ad_campaign("@stats_channel", 3000.0)
        stats = await ad_manager.get_ad_stats()
        assert "campaigns" in stats
        assert "total_budget" in stats
        assert "weekly_budget" in stats
        assert stats["total_budget"] >= 3000.0

    async def test_track_utm(self, initialized_db):
        """track_utm records ad source."""
        await database.get_or_create_client(telegram_id=301, username="utm_user")
        await ad_manager.track_utm(301, "telegram_channel")
        stats = await ad_manager.get_ad_stats()
        sources = [c["source"] for c in stats["campaigns"]]
        assert "telegram_channel" in sources
