"""Парсер маркетплейса Ozon через Seller API."""

import logging
from typing import Any

import httpx

from bot.config import settings

logger = logging.getLogger(__name__)

_OZON_API_BASE = "https://api-seller.ozon.ru"


class OzonParser:
    """Парсер товаров Ozon через Seller API."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=15.0,
            base_url=_OZON_API_BASE,
            headers={
                "Client-Id": settings.ozon_client_id,
                "Api-Key": settings.ozon_api_key,
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        """Закрыть HTTP-клиент."""
        await self._client.aclose()

    async def fetch_product(self, product_id: str) -> dict[str, Any] | None:
        """Получить информацию о товаре по ID.

        Возвращает dict с полями: name, brand, price, old_price,
        discount, rating, feedbacks, product_id. Или None при ошибке.
        """
        try:
            resp = await self._client.post(
                "/v2/product/info",
                json={"product_id": int(product_id)},
            )
            resp.raise_for_status()
            data = resp.json()

            item = data.get("result", {})
            if not item:
                return None

            return self._parse_product(item)
        except Exception as e:
            logger.error("Ошибка при получении товара Ozon %s: %s", product_id, e)
            return None

    async def search_products(
        self, query: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Поиск товаров по запросу.

        Возвращает список dict с информацией о товарах.
        """
        try:
            resp = await self._client.post(
                "/v1/product/list",
                json={
                    "filter": {"visibility": "ALL"},
                    "limit": limit,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get("result", {}).get("items", [])
            result = []
            for item in items[:limit]:
                parsed = self._parse_product(item)
                if parsed:
                    result.append(parsed)
            return result
        except Exception as e:
            logger.error("Ошибка при поиске Ozon '%s': %s", query, e)
            return []

    async def fetch_reviews(self, product_id: str) -> list[str]:
        """Получить отзывы на товар.

        Возвращает список текстов отзывов.
        """
        try:
            resp = await self._client.post(
                "/v1/product/ratings-by-product-id",
                json={"product_id": int(product_id)},
            )
            resp.raise_for_status()
            data = resp.json()

            reviews_data = data.get("reviews", [])
            reviews = []
            for review in reviews_data:
                text = review.get("comment", {}).get("text", "").strip()
                if text:
                    reviews.append(text)
            return reviews
        except Exception as e:
            logger.error("Ошибка при получении отзывов Ozon %s: %s", product_id, e)
            return []

    @staticmethod
    def _parse_product(item: dict[str, Any]) -> dict[str, Any] | None:
        """Распарсить JSON-элемент товара Ozon в удобный dict."""
        try:
            # Цена из поля marketing_price или price
            price = float(item.get("marketing_price", 0) or item.get("price", "0"))
            old_price = float(item.get("old_price", "0") or 0)
            discount = 0
            if old_price > 0:
                discount = round((1 - price / old_price) * 100)

            return {
                "product_id": str(item.get("id", item.get("product_id", ""))),
                "name": item.get("name", item.get("offer_id", "")),
                "brand": item.get("brand", ""),
                "price": price,
                "old_price": old_price,
                "discount": discount,
                "rating": item.get("rating", 0),
                "feedbacks": item.get("reviews_count", 0),
                "marketplace": "ozon",
            }
        except Exception:
            return None
