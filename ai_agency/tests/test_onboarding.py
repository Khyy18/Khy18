"""Tests for onboarding module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import database


@pytest.mark.asyncio
class TestOnboarding:
    """Test onboarding module functionality."""

    async def test_track_onboarding_event(self, initialized_db):
        """track_onboarding_event stores event in DB."""
        import onboarding
        await onboarding._track_onboarding_event(12345, "services_carousel", "view")

        import aiosqlite
        import config
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT * FROM onboarding_events WHERE telegram_id = 12345"
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[2] == "services_carousel"  # step
            assert row[3] == "view"  # action

    async def test_onboarding_steps_defined(self, initialized_db):
        """ONBOARDING_STEPS contains 4 steps."""
        import onboarding
        assert len(onboarding.ONBOARDING_STEPS) == 4
        assert "services_carousel" in onboarding.ONBOARDING_STEPS
        assert "bonus_offer" in onboarding.ONBOARDING_STEPS

    async def test_step_handlers_count(self, initialized_db):
        """STEP_HANDLERS has same count as ONBOARDING_STEPS."""
        import onboarding
        assert len(onboarding.STEP_HANDLERS) == len(onboarding.ONBOARDING_STEPS)

    async def test_get_drop_off_stats(self, initialized_db):
        """get_drop_off_stats returns dict with all steps."""
        import onboarding
        await onboarding._track_onboarding_event(12345, "services_carousel", "view")
        await onboarding._track_onboarding_event(12345, "services_carousel", "skip")

        stats = await onboarding.get_drop_off_stats()
        assert "services_carousel" in stats
        assert stats["services_carousel"]["views"] == 1
        assert stats["services_carousel"]["skips"] == 1
