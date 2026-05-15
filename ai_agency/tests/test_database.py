"""Integration tests for database module with temp SQLite."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import database


@pytest.mark.asyncio
class TestDatabase:
    """Integration tests with temp SQLite database."""

    async def test_init_db_creates_tables(self, initialized_db):
        """init_db creates all required tables."""
        import aiosqlite
        async with aiosqlite.connect(initialized_db.DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in await cursor.fetchall()]
        assert "clients" in tables
        assert "orders" in tables
        assert "payments" in tables
        assert "referrals" in tables
        assert "subscriptions" in tables
        assert "ab_variants" in tables

    async def test_get_or_create_client_creates_new(self, initialized_db):
        """get_or_create_client creates a new client."""
        client = await database.get_or_create_client(
            telegram_id=99999,
            username="newuser",
            first_name="New",
        )
        assert client["telegram_id"] == 99999
        assert client["username"] == "newuser"
        assert client["first_name"] == "New"

    async def test_get_or_create_client_returns_existing(self, sample_client):
        """get_or_create_client returns existing client."""
        client = await database.get_or_create_client(
            telegram_id=12345,
            username="different",
            first_name="Different",
        )
        # Should return the original client data
        assert client["telegram_id"] == 12345
        assert client["username"] == "testuser"

    async def test_create_order_and_get_by_id(self, sample_client):
        """create_order and get_order_by_id work together."""
        order_id = await database.create_order(
            client_id=12345,
            service_type="rewrite",
            input_text="Test text",
            price=100.0,
        )
        assert order_id is not None
        order = await database.get_order_by_id(order_id)
        assert order is not None
        assert order["client_id"] == 12345
        assert order["service_type"] == "rewrite"
        assert order["price"] == 100.0
        assert order["status"] == "pending"

    async def test_update_order_status(self, sample_client):
        """update_order_status changes the status."""
        order_id = await database.create_order(
            client_id=12345,
            service_type="rewrite",
            input_text="Test",
            price=50.0,
        )
        await database.update_order_status(order_id, "completed", "Result text")
        order = await database.get_order_by_id(order_id)
        assert order["status"] == "completed"
        assert order["output_text"] == "Result text"

    async def test_get_client_balance(self, sample_client):
        """get_client_balance returns correct value."""
        balance = await database.get_client_balance(12345)
        assert balance == 0.0

    async def test_update_balance(self, sample_client):
        """update_balance changes balance correctly."""
        await database.update_balance(12345, 250.0)
        balance = await database.get_client_balance(12345)
        assert balance == 250.0

    async def test_credit_referral_bonus(self, initialized_db):
        """credit_referral_bonus works end-to-end."""
        # Create referrer and referred clients
        await database.get_or_create_client(111, "referrer", "Ref")
        await database.get_or_create_client(222, "referred", "New")
        await database.update_balance(111, 100.0)

        # Create referral
        await database.create_referral(111, 222, 0.0)

        # Credit bonus (10% of 500 RUB order)
        bonus = await database.credit_referral_bonus(222, 500.0, 10)
        assert bonus == 50.0

        # Referrer balance increased
        balance = await database.get_client_balance(111)
        assert balance == 150.0
