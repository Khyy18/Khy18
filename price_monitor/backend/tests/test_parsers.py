"""Tests for marketplace parsers (Ozon, Wildberries)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Add project root to sys.path so we can import bot modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bot.parsers.wildberries import WildberriesParser
from bot.parsers.ozon import OzonParser


class TestWildberriesParseProduct:
    """Tests for WildberriesParser._parse_product static method."""

    def test_valid_item_returns_product_dict(self):
        """_parse_product with valid data returns correct fields."""
        item = {
            "id": 12345,
            "name": "Test Item",
            "brand": "TestBrand",
            "salePriceU": 150000,  # 1500.00 rub (in kopecks)
            "priceU": 200000,  # 2000.00 rub
            "sale": 25,
            "rating": 4.5,
            "feedbacks": 100,
        }
        result = WildberriesParser._parse_product(item)

        assert result is not None
        assert result["article_id"] == "12345"
        assert result["name"] == "Test Item"
        assert result["brand"] == "TestBrand"
        assert result["price"] == 1500.0
        assert result["old_price"] == 2000.0
        assert result["discount"] == 25
        assert result["rating"] == 4.5
        assert result["feedbacks"] == 100
        assert result["marketplace"] == "wildberries"

    def test_minimal_item(self):
        """_parse_product with minimal data returns product with defaults."""
        item = {"id": 1, "name": "X"}
        result = WildberriesParser._parse_product(item)

        assert result is not None
        assert result["article_id"] == "1"
        assert result["name"] == "X"
        assert result["price"] == 0.0

    def test_empty_dict_returns_product(self):
        """_parse_product with empty dict still returns a dict with defaults."""
        result = WildberriesParser._parse_product({})
        assert result is not None
        assert result["name"] == ""


class TestWildberriesFetchProduct:
    """Tests for WildberriesParser.fetch_product with mocked HTTP."""

    @pytest.fixture
    def parser(self):
        return WildberriesParser()

    async def test_successful_fetch(self, parser):
        """fetch_product with mock 200 returns parsed product."""
        mock_response = httpx.Response(
            200,
            json={
                "data": {
                    "products": [
                        {
                            "id": 999,
                            "name": "Mocked Product",
                            "brand": "MockBrand",
                            "salePriceU": 100000,
                            "priceU": 120000,
                            "sale": 17,
                            "rating": 4.0,
                            "feedbacks": 50,
                        }
                    ]
                }
            },
            request=httpx.Request("GET", "https://card.wb.ru/cards/v1/detail"),
        )

        with patch.object(parser._client, "get", new_callable=AsyncMock, return_value=mock_response):
            result = await parser.fetch_product("999")

        assert result is not None
        assert result["name"] == "Mocked Product"
        assert result["price"] == 1000.0

    async def test_empty_products_returns_none(self, parser):
        """fetch_product with empty products list returns None."""
        mock_response = httpx.Response(
            200,
            json={"data": {"products": []}},
            request=httpx.Request("GET", "https://card.wb.ru/cards/v1/detail"),
        )

        with patch.object(parser._client, "get", new_callable=AsyncMock, return_value=mock_response):
            result = await parser.fetch_product("000")

        assert result is None

    async def test_429_retry_then_success(self, parser):
        """fetch_product with 429 retries and succeeds on second attempt."""
        # First response: 429
        resp_429 = httpx.Response(
            429,
            headers={"Retry-After": "1"},
            request=httpx.Request("GET", "https://card.wb.ru/cards/v1/detail"),
        )
        # Second response: 200
        resp_200 = httpx.Response(
            200,
            json={
                "data": {
                    "products": [
                        {
                            "id": 111,
                            "name": "After Retry",
                            "brand": "B",
                            "salePriceU": 50000,
                            "priceU": 60000,
                            "sale": 17,
                            "rating": 3.0,
                            "feedbacks": 10,
                        }
                    ]
                }
            },
            request=httpx.Request("GET", "https://card.wb.ru/cards/v1/detail"),
        )

        mock_get = AsyncMock(side_effect=[
            httpx.HTTPStatusError("rate limited", request=resp_429.request, response=resp_429),
            resp_200,
        ])

        with patch.object(parser._client, "get", mock_get), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = await parser.fetch_product("111")

        assert result is not None
        assert result["name"] == "After Retry"


class TestOzonParseData:
    """Tests for OzonParser static/instance parsing methods."""

    def test_parse_seo_data_with_title(self):
        """_parse_seo_data returns product when title exists."""
        seo = {"title": "Ozon Test Product - buy online"}
        result = OzonParser._parse_seo_data(seo, "12345")

        assert result is not None
        assert result["product_id"] == "12345"
        assert result["name"] == "Ozon Test Product - buy online"
        assert result["marketplace"] == "ozon"

    def test_parse_seo_data_no_title(self):
        """_parse_seo_data returns None when title is empty."""
        seo = {"title": ""}
        result = OzonParser._parse_seo_data(seo, "123")
        assert result is None

    def test_extract_product_from_widgets(self):
        """_extract_product_from_widgets with valid heading widget returns product."""
        parser = OzonParser.__new__(OzonParser)
        widget_states = {
            "webProductHeading-123": json.dumps({"title": "Widget Product", "brand": "BrandX"}),
        }
        result = parser._extract_product_from_widgets(widget_states, "555")

        assert result is not None
        assert result["name"] == "Widget Product"
        assert result["product_id"] == "555"
        assert result["marketplace"] == "ozon"

    def test_extract_product_from_widgets_no_match(self):
        """_extract_product_from_widgets with irrelevant widgets returns None."""
        parser = OzonParser.__new__(OzonParser)
        widget_states = {
            "someOtherWidget-999": json.dumps({"foo": "bar"}),
        }
        result = parser._extract_product_from_widgets(widget_states, "111")
        assert result is None


class TestOzonFetchProduct:
    """Tests for OzonParser.fetch_product with mocked HTTP."""

    @pytest.fixture
    def parser(self):
        """Create OzonParser with mocked settings."""
        with patch("bot.parsers.ozon.settings") as mock_settings:
            mock_settings.ozon_client_id = ""
            mock_settings.ozon_api_key = ""
            p = OzonParser()
        return p

    async def test_successful_fetch_via_seo(self, parser):
        """fetch_product with 200 and SEO data returns product."""
        mock_response = httpx.Response(
            200,
            json={
                "widgetStates": {},
                "seo": {"title": "SEO Product Title"},
            },
            request=httpx.Request("GET", "https://api.ozon.ru/composer-api.bx/page/json/v2"),
        )

        with patch.object(parser._client, "get", new_callable=AsyncMock, return_value=mock_response):
            result = await parser.fetch_product("777")

        assert result is not None
        assert result["name"] == "SEO Product Title"
        assert result["product_id"] == "777"

    async def test_successful_fetch_via_widgets(self, parser):
        """fetch_product with 200 and widget data returns product."""
        widget_data = json.dumps({"title": "Widget Found", "brand": "WBrand"})
        mock_response = httpx.Response(
            200,
            json={
                "widgetStates": {"webProductHeading-1": widget_data},
                "seo": {},
            },
            request=httpx.Request("GET", "https://api.ozon.ru/composer-api.bx/page/json/v2"),
        )

        with patch.object(parser._client, "get", new_callable=AsyncMock, return_value=mock_response):
            result = await parser.fetch_product("888")

        assert result is not None
        assert result["name"] == "Widget Found"

    async def test_429_retry_then_success(self, parser):
        """fetch_product with 429 retries after Retry-After."""
        resp_429 = httpx.Response(
            429,
            headers={"Retry-After": "1"},
            request=httpx.Request("GET", "https://api.ozon.ru/composer-api.bx/page/json/v2"),
        )
        resp_200 = httpx.Response(
            200,
            json={
                "widgetStates": {},
                "seo": {"title": "After 429"},
            },
            request=httpx.Request("GET", "https://api.ozon.ru/composer-api.bx/page/json/v2"),
        )

        mock_get = AsyncMock(side_effect=[
            httpx.HTTPStatusError("rate limited", request=resp_429.request, response=resp_429),
            resp_200,
        ])

        with patch.object(parser._client, "get", mock_get), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = await parser.fetch_product("999")

        assert result is not None
        assert result["name"] == "After 429"

    async def test_no_data_returns_none(self, parser):
        """fetch_product returns None when no widgets or SEO data."""
        mock_response = httpx.Response(
            200,
            json={"widgetStates": {}, "seo": {}},
            request=httpx.Request("GET", "https://api.ozon.ru/composer-api.bx/page/json/v2"),
        )

        with patch.object(parser._client, "get", new_callable=AsyncMock, return_value=mock_response):
            result = await parser.fetch_product("000")

        assert result is None
