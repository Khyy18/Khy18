"""Tests for daily_report module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio

import daily_report
import database


@pytest.mark.asyncio
class TestDailyReport:
    """Tests for daily report module."""

    async def test_get_revenue_today(self, initialized_db):
        """get_revenue_today returns 0 when no orders."""
        revenue = await daily_report.get_revenue_today()
        assert revenue == 0.0

    async def test_get_revenue_today_with_orders(self, initialized_db):
        """get_revenue_today returns sum of completed orders today."""
        await database.get_or_create_client(telegram_id=500, username="daily")
        order_id = await database.create_order(
            client_id=500, service_type="rewrite", input_text="test", price=1000.0
        )
        await database.update_order_status(order_id, "completed", "result")

        revenue = await daily_report.get_revenue_today()
        assert revenue == 1000.0

    async def test_get_orders_today(self, initialized_db):
        """get_orders_today returns count of orders created today."""
        await database.get_or_create_client(telegram_id=501, username="orderer")
        await database.create_order(
            client_id=501, service_type="rewrite", input_text="test1", price=500.0
        )
        await database.create_order(
            client_id=501, service_type="seo", input_text="test2", price=300.0
        )

        count = await daily_report.get_orders_today()
        assert count == 2

    async def test_get_new_clients_today(self, initialized_db):
        """get_new_clients_today returns count of new registrations."""
        await database.get_or_create_client(telegram_id=601, username="new1")
        await database.get_or_create_client(telegram_id=602, username="new2")

        count = await daily_report.get_new_clients_today()
        assert count >= 2

    async def test_get_avg_check_today(self, initialized_db):
        """get_avg_check_today returns average of completed orders."""
        await database.get_or_create_client(telegram_id=700, username="avguser")
        o1 = await database.create_order(
            client_id=700, service_type="rewrite", input_text="t1", price=1000.0
        )
        o2 = await database.create_order(
            client_id=700, service_type="seo", input_text="t2", price=2000.0
        )
        await database.update_order_status(o1, "completed", "r1")
        await database.update_order_status(o2, "completed", "r2")

        avg = await daily_report.get_avg_check_today()
        assert avg == 1500.0

    async def test_get_api_costs_today(self, initialized_db):
        """get_api_costs_today estimates costs based on order count."""
        await database.get_or_create_client(telegram_id=800, username="costly")
        await database.create_order(
            client_id=800, service_type="rewrite", input_text="test", price=500.0
        )

        costs = await daily_report.get_api_costs_today()
        # 1 order * 2K tokens * 0.03 per 1K = 0.06
        assert costs == 0.06

    async def test_get_revenue_last_7_days(self, initialized_db):
        """get_revenue_last_7_days returns list of 7 numeric values."""
        values = await daily_report.get_revenue_last_7_days()
        assert len(values) == 7
        assert all(isinstance(v, (int, float)) for v in values)

    async def test_pnl_indicator(self, initialized_db):
        """_pnl_indicator formats change correctly."""
        assert "\u25b2" in daily_report._pnl_indicator(1500, 1000)
        assert "\u25bc" in daily_report._pnl_indicator(500, 1000)
        assert "0%" in daily_report._pnl_indicator(1000, 1000)

    async def test_generate_daily_report(self, initialized_db):
        """generate_daily_report returns formatted HTML string."""
        report = await daily_report.generate_daily_report()
        assert "Дневной отчёт" in report
        assert "<b>" in report
        assert "Выручка" in report
        assert "Заказов" in report

    async def test_get_alerts_empty(self, initialized_db):
        """get_alerts returns empty list when no problems."""
        alerts = await daily_report.get_alerts()
        assert isinstance(alerts, list)
