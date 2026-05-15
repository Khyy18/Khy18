"""Tests for money-back / refund in billing module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, patch

import billing
import database


@pytest.mark.asyncio
class TestMoneyback:

    async def test_refund_to_balance_success(self, initialized_db, sample_client):
        """Create order, refund it, verify balance increased and status is 'refunded'."""
        telegram_id = 12345

        # Top up balance first so we can create an order with a price
        await billing.top_up_balance(telegram_id, 1000.0, method="test")

        # Create an order with a price
        order_id = await database.create_order(
            client_id=telegram_id,
            service_type="copywriting",
            input_text="Test order",
            price=500.0,
        )
        await database.update_order_status(order_id, "completed")

        # Charge the client for the order
        charged = await billing.charge_client(telegram_id, 500.0)
        assert charged is True

        # Balance should be 500 now
        balance_before = await database.get_client_balance(telegram_id)
        assert balance_before == 500.0

        # Refund
        result = await billing.refund_to_balance(telegram_id, order_id)
        assert result is True

        # Check balance increased
        balance_after = await database.get_client_balance(telegram_id)
        assert balance_after == 1000.0

        # Check order status
        order = await database.get_order_by_id(order_id)
        assert order["status"] == "refunded"

    async def test_refund_to_balance_no_order(self, initialized_db, sample_client):
        """Non-existent order returns False."""
        result = await billing.refund_to_balance(12345, 99999)
        assert result is False

    async def test_get_moneyback_stats(self, initialized_db, sample_client):
        """After some refunds, verify stats dict."""
        telegram_id = 12345

        # Top up balance
        await billing.top_up_balance(telegram_id, 2000.0, method="test")

        # Create some orders
        order1_id = await database.create_order(
            client_id=telegram_id,
            service_type="copywriting",
            input_text="Order 1",
            price=300.0,
        )
        order2_id = await database.create_order(
            client_id=telegram_id,
            service_type="rewrite",
            input_text="Order 2",
            price=200.0,
        )
        order3_id = await database.create_order(
            client_id=telegram_id,
            service_type="seo",
            input_text="Order 3",
            price=100.0,
        )

        # Complete all orders
        await database.update_order_status(order1_id, "completed")
        await database.update_order_status(order2_id, "completed")
        await database.update_order_status(order3_id, "completed")

        # Refund 2 orders
        await billing.refund_to_balance(telegram_id, order1_id)
        await billing.refund_to_balance(telegram_id, order2_id)

        stats = await billing.get_moneyback_stats()

        assert stats["total_refunds"] == 2
        assert stats["total_amount_refunded"] == 500.0
        # 2 refunded out of 3 total orders
        assert stats["refund_rate"] == pytest.approx(66.66, abs=1.0)

    async def test_refund_zero_price_order(self, initialized_db, sample_client):
        """Refund on an order with 0 price returns False."""
        telegram_id = 12345

        order_id = await database.create_order(
            client_id=telegram_id,
            service_type="copywriting",
            input_text="Free order",
            price=0.0,
        )
        await database.update_order_status(order_id, "completed")

        result = await billing.refund_to_balance(telegram_id, order_id)
        assert result is False
