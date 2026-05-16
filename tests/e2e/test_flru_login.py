"""E2E тесты для FLruPlatform с mock-сервером."""

import json

import pytest

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from freelance_automation.base import Order
from freelance_automation.flru import FLruPlatform

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not HAS_PLAYWRIGHT, reason="playwright not installed"),
]


@pytest.mark.asyncio
async def test_fetch_new_orders_from_mock(mock_server, cookies_file):
    """FLruPlatform парсит заказы из mock HTML."""
    base_url = f"http://localhost:{mock_server.port}/flru"

    platform = FLruPlatform()
    # Подменяем URL для теста
    platform.BASE_URL = base_url
    platform.PROJECTS_URL = f"{base_url}/projects/"

    try:
        logged_in = await platform.login(cookies_file)
        assert logged_in is True

        orders = await platform.fetch_new_orders()
        assert len(orders) == 2
        assert orders[0].title == "Создание веб-приложения"
        assert orders[0].budget == 15000.0
        assert orders[1].title == "Мобильное приложение"
        assert orders[1].budget == 50000.0
    finally:
        await platform.close()


@pytest.mark.asyncio
async def test_respond_to_order_fills_form(mock_server, cookies_file):
    """FLruPlatform заполняет форму отклика на mock-сервере."""
    base_url = f"http://localhost:{mock_server.port}/flru"

    platform = FLruPlatform()
    platform.BASE_URL = base_url
    platform.PROJECTS_URL = f"{base_url}/projects/"

    try:
        logged_in = await platform.login(cookies_file)
        assert logged_in is True

        order = Order(
            id="fl-project-1",
            title="Создание веб-приложения",
            description="Веб-приложение",
            budget=15000.0,
            url=f"{base_url}/projects/fl-project-1",
        )
        result = await platform.respond_to_order(order, "Могу сделать!")
        assert result is True
    finally:
        await platform.close()


@pytest.mark.asyncio
async def test_fetch_with_keywords_filter(mock_server, cookies_file):
    """FLruPlatform фильтрует заказы по ключевым словам."""
    base_url = f"http://localhost:{mock_server.port}/flru"

    platform = FLruPlatform()
    platform.BASE_URL = base_url
    platform.PROJECTS_URL = f"{base_url}/projects/"

    try:
        logged_in = await platform.login(cookies_file)
        assert logged_in is True

        orders = await platform.fetch_new_orders(keywords=["django"])
        assert len(orders) == 1
        assert "веб-приложения" in orders[0].title
    finally:
        await platform.close()
