"""Tests for demand_pricing module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from datetime import datetime

import database


@pytest.mark.asyncio
class TestDemandPricing:
    """Test demand pricing module functionality."""

    async def test_normal_pricing(self, initialized_db):
        """Normal hours with no orders returns multiplier 1.0."""
        import demand_pricing

        with patch.object(demand_pricing, "_is_off_peak", return_value=False):
            multiplier, label = await demand_pricing.get_demand_multiplier("copywriting")
            assert multiplier == 1.0
            assert label == ""

    async def test_surge_pricing(self, initialized_db):
        """High order count triggers surge pricing."""
        import demand_pricing
        import config

        # Insert many orders to trigger surge
        import aiosqlite
        from datetime import datetime, timedelta
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(config.DATABASE_PATH) as db:
            for i in range(15):
                await db.execute(
                    "INSERT INTO orders (client_id, service_type, input_text, price, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (12345, "copywriting", "test", 100.0, "pending", now),
                )
            await db.commit()

        with patch.object(demand_pricing, "_is_off_peak", return_value=False):
            multiplier, label = await demand_pricing.get_demand_multiplier("copywriting")
            assert multiplier > 1.0
            assert "Surge" in label

    async def test_night_discount(self, initialized_db):
        """Off-peak hours with low orders gives discount."""
        import demand_pricing

        with patch.object(demand_pricing, "_is_off_peak", return_value=True):
            multiplier, label = await demand_pricing.get_demand_multiplier("copywriting")
            assert multiplier < 1.0
            assert "discount" in label.lower() or "Night" in label

    async def test_is_off_peak_night_hours(self, initialized_db):
        """_is_off_peak returns True for night hours."""
        import demand_pricing
        from unittest.mock import patch
        from datetime import datetime

        # Mock datetime to return 3 AM
        mock_dt = datetime(2024, 1, 15, 3, 0, 0)  # Monday 3AM
        with patch.object(demand_pricing, "datetime") as mock_datetime:
            mock_datetime.utcnow.return_value = mock_dt
            result = demand_pricing._is_off_peak()
            assert result is True
