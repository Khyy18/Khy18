"""Tests for sales_funnel module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

import database
import sales_funnel
from sales_funnel import FunnelStage


@pytest.mark.asyncio
class TestSalesFunnel:
    """Tests for sales funnel module."""

    async def test_record_funnel_event(self, initialized_db):
        """record_funnel_event stores event in database."""
        await database.get_or_create_client(100, "user1", "User")
        await sales_funnel.record_funnel_event(100, FunnelStage.AWARENESS)

        import aiosqlite
        async with aiosqlite.connect(initialized_db.DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT * FROM funnel_events WHERE client_id = 100"
            )
            rows = await cursor.fetchall()
        assert len(rows) == 1
        assert rows[0][2] == "awareness"  # stage column

    async def test_get_funnel_stats(self, initialized_db):
        """get_funnel_stats returns correct statistics."""
        await database.get_or_create_client(200, "user2", "User2")
        await sales_funnel.record_funnel_event(200, FunnelStage.AWARENESS)
        await sales_funnel.record_funnel_event(200, FunnelStage.AWARENESS, converted=True)

        stats = await sales_funnel.get_funnel_stats()
        assert "awareness" in stats
        assert stats["awareness"]["total"] == 2
        assert stats["awareness"]["converted"] == 1

    async def test_welcome_trigger_sends_message(self, initialized_db, monkeypatch):
        """welcome_trigger sends message to new user."""
        monkeypatch.setattr("config.FUNNEL_ENABLED", True)
        await database.get_or_create_client(300, "user3", "TestUser")

        # Get client data and set registration time to 2 minutes ago
        client = await database.get_or_create_client(300, "user3", "TestUser")
        from datetime import datetime, timedelta
        old_time = (datetime.utcnow() - timedelta(minutes=2)).isoformat()
        client["registered_at"] = old_time

        bot = AsyncMock()
        bot.send_message = AsyncMock()

        result = await sales_funnel.welcome_trigger(bot, client)
        assert result is True
        bot.send_message.assert_called_once()

    async def test_welcome_trigger_no_duplicate(self, initialized_db, monkeypatch):
        """welcome_trigger does not send duplicate messages."""
        monkeypatch.setattr("config.FUNNEL_ENABLED", True)
        await database.get_or_create_client(400, "user4", "User4")
        client = await database.get_or_create_client(400, "user4", "User4")
        from datetime import datetime, timedelta
        old_time = (datetime.utcnow() - timedelta(minutes=2)).isoformat()
        client["registered_at"] = old_time

        bot = AsyncMock()
        bot.send_message = AsyncMock()

        # First call should trigger
        await sales_funnel.welcome_trigger(bot, client)
        # Second call should not trigger (already sent)
        result = await sales_funnel.welcome_trigger(bot, client)
        assert result is False

    async def test_funnel_disabled(self, initialized_db, monkeypatch):
        """Triggers do nothing when FUNNEL_ENABLED is False."""
        monkeypatch.setattr("config.FUNNEL_ENABLED", False)
        await database.get_or_create_client(500, "user5", "User5")
        client = await database.get_or_create_client(500, "user5", "User5")

        bot = AsyncMock()
        result = await sales_funnel.welcome_trigger(bot, client)
        assert result is False
