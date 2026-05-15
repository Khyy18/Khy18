"""Tests for A/B testing module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import ab_testing


@pytest.mark.asyncio
class TestABTesting:
    """Test A/B testing logic."""

    async def test_select_variant_none_when_empty(self, initialized_db):
        """select_variant returns None when no variants exist."""
        result = await ab_testing.select_variant("rewrite")
        assert result is None

    async def test_select_variant_returns_variant(self, initialized_db):
        """select_variant returns a variant after adding one."""
        await ab_testing.add_variant("rewrite", "v1", "Test prompt")
        result = await ab_testing.select_variant("rewrite")
        assert result is not None
        variant_id, system_prompt = result
        assert system_prompt == "Test prompt"

    async def test_ucb1_exploration(self, initialized_db):
        """Variant with <5 uses gets selected (exploration)."""
        # Add two variants
        v1_id = await ab_testing.add_variant("copywriting", "v1", "Prompt A")
        v2_id = await ab_testing.add_variant("copywriting", "v2", "Prompt B")

        # First selection should pick first variant (exploration, <5 uses)
        result = await ab_testing.select_variant("copywriting")
        assert result is not None
        # It should pick one of them (first with <5 uses)
        assert result[1] in ["Prompt A", "Prompt B"]

    async def test_record_result_increments_score(self, initialized_db):
        """record_result increments total_score."""
        variant_id = await ab_testing.add_variant("seo", "v1", "SEO prompt")
        await ab_testing.record_result(variant_id, 5)
        await ab_testing.record_result(variant_id, 3)

        # Check that score was incremented
        import aiosqlite
        import config
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT total_score FROM ab_variants WHERE id = ?", (variant_id,)
            )
            row = await cursor.fetchone()
            assert row[0] == 8.0

    async def test_get_best_variant_none_insufficient_data(self, initialized_db):
        """get_best_variant returns None when insufficient data."""
        await ab_testing.add_variant("summary", "v1", "Summary prompt")
        # No uses, so total_uses < 10
        result = await ab_testing.get_best_variant("summary")
        assert result is None

    async def test_get_best_variant_returns_best(self, initialized_db):
        """get_best_variant returns best when enough data."""
        import aiosqlite
        import config

        v1_id = await ab_testing.add_variant("translation", "v1", "Trans prompt A")
        v2_id = await ab_testing.add_variant("translation", "v2", "Trans prompt B")

        # Directly set total_uses and total_score for testing
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            await db.execute(
                "UPDATE ab_variants SET total_uses = 15, total_score = 60 WHERE id = ?",
                (v1_id,),
            )
            await db.execute(
                "UPDATE ab_variants SET total_uses = 12, total_score = 36 WHERE id = ?",
                (v2_id,),
            )
            await db.commit()

        result = await ab_testing.get_best_variant("translation")
        assert result is not None
        # v1 avg = 4.0, v2 avg = 3.0, so v1 is best
        assert result["variant_name"] == "v1"
