"""Tests for whitelabel module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import whitelabel
import database


@pytest.mark.asyncio
class TestWhitelabel:
    """Tests for white-label B2B system."""

    async def test_init_whitelabel_tables(self, initialized_db):
        """init_whitelabel_tables creates necessary tables."""
        await whitelabel.init_whitelabel_tables()
        # Should not raise - tables already exist from init_db

    async def test_create_whitelabel_bot(self, initialized_db):
        """create_whitelabel_bot creates a bot record."""
        await whitelabel.init_whitelabel_tables()
        bot_id = await whitelabel.create_whitelabel_bot(
            owner_id=12345,
            token="123:ABC",
            bot_name="TestBot",
            persona="Test Persona",
            allowed_services=["copywriting", "rewrite"],
            pricing_multiplier=1.5,
            revenue_share=0.25,
        )
        assert bot_id > 0

    async def test_get_whitelabel_bots(self, initialized_db):
        """get_whitelabel_bots returns active bots."""
        await whitelabel.init_whitelabel_tables()
        await whitelabel.create_whitelabel_bot(
            owner_id=12345,
            token="123:XYZ",
            bot_name="ActiveBot",
        )
        bots = await whitelabel.get_whitelabel_bots(active_only=True)
        assert len(bots) >= 1
        assert bots[0]["bot_name"] == "ActiveBot"
        assert isinstance(bots[0]["allowed_services"], list)

    async def test_get_whitelabel_stats(self, initialized_db):
        """get_whitelabel_stats returns stats dict."""
        await whitelabel.init_whitelabel_tables()
        bot_id = await whitelabel.create_whitelabel_bot(
            owner_id=12345,
            token="123:STAT",
            bot_name="StatBot",
        )
        stats = await whitelabel.get_whitelabel_stats(bot_id)
        assert stats["total_orders"] == 0
        assert stats["total_revenue"] == 0
        assert stats["total_owner_share"] == 0

    async def test_record_whitelabel_revenue(self, initialized_db):
        """record_whitelabel_revenue records revenue entry."""
        await whitelabel.init_whitelabel_tables()
        bot_id = await whitelabel.create_whitelabel_bot(
            owner_id=12345,
            token="123:REV",
            bot_name="RevBot",
        )
        await whitelabel.record_whitelabel_revenue(bot_id, 1, 100.0, 0.3)
        stats = await whitelabel.get_whitelabel_stats(bot_id)
        assert stats["total_revenue"] == 100.0
        assert stats["total_owner_share"] == 30.0

    async def test_deactivate_bot(self, initialized_db):
        """deactivate_bot marks bot as inactive."""
        await whitelabel.init_whitelabel_tables()
        bot_id = await whitelabel.create_whitelabel_bot(
            owner_id=12345,
            token="123:DEACT",
            bot_name="DeactBot",
        )
        await whitelabel.deactivate_bot(bot_id)
        bots = await whitelabel.get_whitelabel_bots(active_only=True)
        bot_ids = [b["id"] for b in bots]
        assert bot_id not in bot_ids
