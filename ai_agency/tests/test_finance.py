"""Tests for finance module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import database
import finance


@pytest.mark.asyncio
class TestFinance:
    """Tests for finance module."""

    async def test_calculate_pnl_empty(self, initialized_db):
        """calculate_pnl returns zeros when no data."""
        pnl = await finance.calculate_pnl(30)
        assert pnl["revenue"] == 0.0
        assert pnl["api_costs"] == 0.0
        assert pnl["net_profit"] == 0.0
        assert pnl["order_count"] == 0

    async def test_calculate_pnl_with_orders(self, initialized_db):
        """calculate_pnl calculates correctly with orders."""
        await database.get_or_create_client(100, "user1", "User")
        order_id = await database.create_order(100, "rewrite", "text", 500.0)
        await database.update_order_status(order_id, "completed", "result")

        pnl = await finance.calculate_pnl(30)
        assert pnl["revenue"] == 500.0
        assert pnl["order_count"] == 1
        assert pnl["api_costs"] > 0  # Should have some API cost
        assert pnl["net_profit"] == pnl["revenue"] - pnl["total_expenses"]

    async def test_add_and_get_expenses(self, initialized_db):
        """add_expense and get_expenses work correctly."""
        expense_id = await finance.add_expense("advertising", 1000.0, "Facebook Ads")
        assert expense_id is not None

        expenses = await finance.get_expenses(30)
        assert len(expenses) == 1
        assert expenses[0]["category"] == "advertising"
        assert expenses[0]["amount"] == 1000.0
        assert expenses[0]["description"] == "Facebook Ads"

    async def test_forecast_revenue_empty(self, initialized_db):
        """forecast_revenue_month returns zeros when no data."""
        forecast = await finance.forecast_revenue_month()
        assert forecast["daily_avg"] == 0.0
        assert forecast["monthly_forecast"] == 0.0

    async def test_get_service_margins(self, initialized_db):
        """get_service_margins returns margins per service."""
        await database.get_or_create_client(200, "user2", "User2")
        order_id = await database.create_order(200, "copywriting", "text", 300.0)
        await database.update_order_status(order_id, "completed", "result")

        margins = await finance.get_service_margins()
        assert len(margins) == 1
        assert margins[0]["service_type"] == "copywriting"
        assert margins[0]["revenue"] == 300.0
        assert margins[0]["margin_percent"] > 0

    async def test_format_pnl_card(self, initialized_db):
        """format_pnl_card returns formatted string."""
        pnl = await finance.calculate_pnl(30)
        card = finance.format_pnl_card(pnl)
        assert "P&L" in card
        assert "Выручка" in card
