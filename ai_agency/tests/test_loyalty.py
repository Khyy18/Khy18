"""Tests for loyalty module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import database


@pytest.mark.asyncio
class TestLoyalty:
    """Test loyalty module functionality."""

    async def test_bronze_level_default(self, sample_client):
        """New client (0 spent) has bronze level."""
        import loyalty
        level = await loyalty.get_loyalty_level(12345)
        assert level["name"] == "bronze"
        assert level["discount"] == 0.0

    async def test_silver_level(self, initialized_db):
        """Client with 2000 spent has silver level."""
        import loyalty
        import aiosqlite
        import config

        await database.get_or_create_client(99999, "silver_user", "Silver")
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute(
                "UPDATE clients SET total_spent = 2000.0 WHERE telegram_id = 99999"
            )
            await db.commit()

        level = await loyalty.get_loyalty_level(99999)
        assert level["name"] == "silver"
        assert level["discount"] == 0.05

    async def test_gold_level(self, initialized_db):
        """Client with 8000 spent has gold level."""
        import loyalty
        import aiosqlite
        import config

        await database.get_or_create_client(88888, "gold_user", "Gold")
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute(
                "UPDATE clients SET total_spent = 8000.0 WHERE telegram_id = 88888"
            )
            await db.commit()

        level = await loyalty.get_loyalty_level(88888)
        assert level["name"] == "gold"
        assert level["discount"] == 0.10

    async def test_platinum_level(self, initialized_db):
        """Client with 20000 spent has platinum level."""
        import loyalty
        import aiosqlite
        import config

        await database.get_or_create_client(77777, "plat_user", "Plat")
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute(
                "UPDATE clients SET total_spent = 20000.0 WHERE telegram_id = 77777"
            )
            await db.commit()

        level = await loyalty.get_loyalty_level(77777)
        assert level["name"] == "platinum"
        assert level["discount"] == 0.15

    async def test_get_loyalty_discount(self, sample_client):
        """get_loyalty_discount returns 0.0 for bronze."""
        import loyalty
        discount = await loyalty.get_loyalty_discount(12345)
        assert discount == 0.0

    async def test_get_loyalty_info_returns_html(self, sample_client):
        """get_loyalty_info returns HTML card string."""
        import loyalty
        info_text = await loyalty.get_loyalty_info(12345)
        assert "<b>" in info_text
        assert "Bronze" in info_text or "bronze" in info_text.lower()

    async def test_check_level_up_no_change(self, sample_client):
        """check_level_up returns None if no level change."""
        import loyalty
        result = await loyalty.check_level_up(12345, 500.0)
        assert result is None

    async def test_check_level_up_triggered(self, initialized_db):
        """check_level_up returns notification text on level up."""
        import loyalty
        import aiosqlite
        import config

        await database.get_or_create_client(66666, "up_user", "Up")
        # loyalty_notified_level defaults to 'bronze'
        result = await loyalty.check_level_up(66666, 1500.0)
        assert result is not None
        assert "Silver" in result or "silver" in result.lower()
