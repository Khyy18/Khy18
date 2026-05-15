"""Tests for retargeting module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import database


@pytest.mark.asyncio
class TestRetargeting:
    """Test retargeting module functionality."""

    async def test_track_event(self, initialized_db):
        """track_event stores event in user_events table."""
        import retargeting
        await retargeting.track_event(12345, "start")

        import aiosqlite
        import config
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT * FROM user_events WHERE telegram_id = 12345 AND event_type = 'start'"
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[2] == "start"  # event_type

    async def test_cooldown_logic(self, initialized_db):
        """After retargeting_sent event, cooldown prevents re-sending."""
        import retargeting
        from datetime import datetime

        import aiosqlite
        import config

        # Simulate a recent retargeting_sent event
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute(
                "INSERT INTO user_events (telegram_id, event_type, timestamp, processed) VALUES (?, ?, ?, 1)",
                (12345, "retargeting_sent", now),
            )
            await db.commit()

        # Cooldown should prevent sending
        can_send = await retargeting._check_cooldown(12345)
        assert can_send is False

    async def test_cooldown_expired(self, initialized_db):
        """After cooldown period expires, can send again."""
        import retargeting
        from datetime import datetime, timedelta

        import aiosqlite
        import config

        # Simulate an old retargeting_sent event (2 days ago)
        old_time = (datetime.utcnow() - timedelta(days=2)).isoformat()
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute(
                "INSERT INTO user_events (telegram_id, event_type, timestamp, processed) VALUES (?, ?, ?, 1)",
                (99999, "retargeting_sent", old_time),
            )
            await db.commit()

        # Cooldown should be expired
        can_send = await retargeting._check_cooldown(99999)
        assert can_send is True

    async def test_scenarios_defined(self, initialized_db):
        """SCENARIOS contains expected event types."""
        import retargeting
        event_types = [s[0] for s in retargeting.SCENARIOS]
        assert "start" in event_types
        assert "order_started" in event_types
        assert "marketplace_view" in event_types
        assert "low_rating" in event_types
