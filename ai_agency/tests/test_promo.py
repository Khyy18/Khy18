"""Tests for promo module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from datetime import datetime, timedelta

import database
import promo


@pytest.mark.asyncio
class TestPromo:
    """Tests for promo code module."""

    async def test_create_and_validate_promo(self, initialized_db):
        """create_promo and validate_promo work together."""
        promo_id = await promo.create_promo(
            code="TEST10",
            discount_type="percentage",
            discount_value=10.0,
            max_uses=100,
        )
        assert promo_id is not None

        result = await promo.validate_promo("TEST10")
        assert result is not None
        assert result["code"] == "TEST10"
        assert result["discount_value"] == 10.0

    async def test_apply_promo_percentage(self, initialized_db):
        """apply_promo applies percentage discount correctly."""
        await promo.create_promo("SAVE20", "percentage", 20.0, 100)

        new_price, promo_data = await promo.apply_promo("SAVE20", 1000.0)
        assert new_price == 800.0
        assert promo_data is not None
        assert promo_data["code"] == "SAVE20"

    async def test_apply_promo_fixed(self, initialized_db):
        """apply_promo applies fixed discount correctly."""
        await promo.create_promo("FLAT500", "fixed", 500.0, 100)

        new_price, promo_data = await promo.apply_promo("FLAT500", 1000.0)
        assert new_price == 500.0

    async def test_validate_promo_expired(self, initialized_db):
        """validate_promo rejects expired promo codes."""
        expired = (datetime.utcnow() - timedelta(days=1)).isoformat()
        await promo.create_promo("EXPIRED", "percentage", 10.0, 100, expires_at=expired)

        result = await promo.validate_promo("EXPIRED")
        assert result is None

    async def test_validate_promo_max_uses(self, initialized_db):
        """validate_promo rejects promo codes that reached max uses."""
        await promo.create_promo("LIMITED", "percentage", 10.0, max_uses=1)

        # First use should work
        new_price, promo_data = await promo.apply_promo("LIMITED", 100.0)
        assert promo_data is not None

        # Second use should fail (max_uses=1, used_count now 1)
        result = await promo.validate_promo("LIMITED")
        assert result is None

    async def test_delete_promo(self, initialized_db):
        """delete_promo deactivates the code."""
        await promo.create_promo("TODEL", "percentage", 5.0, 100)
        deleted = await promo.delete_promo("TODEL")
        assert deleted is True

        result = await promo.validate_promo("TODEL")
        assert result is None

    async def test_list_promos(self, initialized_db):
        """list_promos returns active promo codes."""
        await promo.create_promo("LIST1", "percentage", 10.0, 100)
        await promo.create_promo("LIST2", "fixed", 200.0, 50)

        promos = await promo.list_promos()
        codes = [p["code"] for p in promos]
        assert "LIST1" in codes
        assert "LIST2" in codes

    async def test_partner_earnings(self, initialized_db):
        """record_partner_earning and get_partner_stats work."""
        await database.get_or_create_client(1000, "partner", "Partner")
        await database.get_or_create_client(2000, "referred", "Referred")

        commission = await promo.record_partner_earning(
            partner_id=1000,
            referred_client_id=2000,
            order_id=1,
            order_amount=500.0,
        )
        assert commission == 50.0  # 10% by default

        stats = await promo.get_partner_stats(1000)
        assert stats["total_earnings"] == 50.0
        assert stats["referred_clients"] == 1
        assert stats["total_orders"] == 1
