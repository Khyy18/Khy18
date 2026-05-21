"""Парсер маркетплейса Wildberries через публичный API."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Публичные API-эндпоинты WB
_DETAIL_URL = "https://card.wb.ru/cards/v1/detail"
_SEARCH_URL = "https://search.wb.ru/exactmatch/ru/common/v4/search"


class WildberriesParser:
    """Парсер товаров Wildberries."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=15.0,
            headers={"Accept": "application/json"},
        )

    async def close(self) -> None:
        """Закрыть HTTP-клиент."""
        await self._client.aclose()

    async def fetch_product(self, article_id: str) -> dict[str, Any] | None:
        """Получить информацию о товаре по артикулу.

        Возвращает dict с полями: name, brand, price, old_price,
        discount, rating, feedbacks, article_id. Или None при ошибке.
        """
        try:
            resp = await self._client.get(
                _DETAIL_URL,
                params={
                    "appType": "1",
                    "curr": "rub",
                    "nm": article_id,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            products = data.get("data", {}).get("products", [])
            if not products:
                return None

            item = products[0]
            return self._parse_product(item)
        except Exception as e:
            logger.error("Ошибка при получении товара WB %s: %s", article_id, e)
            return None

    async def search_products(
        self, query: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Поиск товаров по запросу.

        Возвращает список dict с информацией о товарах.
        """
        try:
            resp = await self._client.get(
                _SEARCH_URL,
                params={
                    "query": query,
                    "resultset": "catalog",
                    "limit": limit,
                    "sort": "popular",
                    "appType": "1",
                    "curr": "rub",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            products = data.get("data", {}).get("products", [])
            result = []
            for item in products[:limit]:
                parsed = self._parse_product(item)
                if parsed:
                    result.append(parsed)
            return result
        except Exception as e:
            logger.error("Ошибка при поиске WB '%s': %s", query, e)
            return []

    async def fetch_reviews(self, article_id: str) -> list[str]:
        """Получить отзывы на товар.

        Возвращает список текстов отзывов.
        """
        try:
            url = f"https://feedbacks1.wb.ru/feedbacks/v1/{article_id}"
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()

            feedbacks = data.get("feedbacks", [])
            reviews = []
            for fb in feedbacks:
                text = fb.get("text", "").strip()
                if text:
                    reviews.append(text)
            return reviews
        except Exception as e:
            logger.error("Ошибка при получении отзывов WB %s: %s", article_id, e)
            return []

    @staticmethod
    def _parse_product(item: dict[str, Any]) -> dict[str, Any] | None:
        """Распарсить JSON-элемент товара в удобный dict."""
        try:
            # Цены в API хранятся в копейках (salePriceU, priceU)
            sale_price = item.get("salePriceU", 0) / 100
            original_price = item.get("priceU", 0) / 100

            return {
                "article_id": str(item.get("id", "")),
                "name": item.get("name", ""),
                "brand": item.get("brand", ""),
                "price": sale_price,
                "old_price": original_price,
                "discount": item.get("sale", 0),
                "rating": item.get("rating", 0),
                "feedbacks": item.get("feedbacks", 0),
                "marketplace": "wildberries",
            }
        except Exception:
            return None
