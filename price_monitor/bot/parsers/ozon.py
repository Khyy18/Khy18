"""Парсер маркетплейса Ozon через публичные эндпоинты."""

import asyncio
import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log

from bot.config import settings

logger = logging.getLogger(__name__)

# Публичный API Ozon для получения данных о товарах
_OZON_PUBLIC_BASE = "https://api.ozon.ru/composer-api.bx/page/json/v2"


class OzonParser:
    """Парсер товаров Ozon через публичные эндпоинты каталога."""

    def __init__(self) -> None:
        headers: dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        # Опциональные заголовки для расширенного доступа
        if settings.ozon_client_id:
            headers["Client-Id"] = settings.ozon_client_id
        if settings.ozon_api_key:
            headers["Api-Key"] = settings.ozon_api_key

        self._client = httpx.AsyncClient(
            timeout=15.0,
            headers=headers,
        )

    async def close(self) -> None:
        """Закрыть HTTP-клиент."""
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=9),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def fetch_product(self, product_id: str) -> dict[str, Any] | None:
        """Получить информацию о товаре по ID через публичный каталог.

        Возвращает dict с полями: name, brand, price, old_price,
        discount, rating, feedbacks, product_id. Или None при ошибке.
        """
        max_429_retries = 2
        for _attempt_429 in range(max_429_retries + 1):
            try:
                resp = await self._client.get(
                    _OZON_PUBLIC_BASE,
                    params={"url": f"/product/{product_id}"},
                )
                resp.raise_for_status()
                data = resp.json()

                # Извлекаем данные о товаре из ответа публичного API
                widget_states = data.get("widgetStates", {})
                product_info = self._extract_product_from_widgets(widget_states, product_id)
                if product_info:
                    return product_info

                # Fallback: пробуем найти в seo или layout
                seo = data.get("seo", {})
                if seo:
                    return self._parse_seo_data(seo, product_id)

                return None
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and _attempt_429 < max_429_retries:
                    retry_after = int(e.response.headers.get("Retry-After", "60"))
                    logger.warning("Ozon rate limited (429), waiting %d sec", retry_after)
                    await asyncio.sleep(retry_after)
                    continue
                raise
            except Exception as e:
                logger.error("Ошибка при получении товара Ozon %s: %s", product_id, e)
                raise
        return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=9),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def search_products(
        self, query: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Поиск товаров по запросу через публичный каталог.

        Возвращает список dict с информацией о товарах.
        """
        max_429_retries = 2
        for _attempt_429 in range(max_429_retries + 1):
            try:
                resp = await self._client.get(
                    _OZON_PUBLIC_BASE,
                    params={"url": f"/search/?text={query}&from_global=true"},
                )
                resp.raise_for_status()
                data = resp.json()

                widget_states = data.get("widgetStates", {})
                results = self._extract_search_results(widget_states, limit)
                return results
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and _attempt_429 < max_429_retries:
                    retry_after = int(e.response.headers.get("Retry-After", "60"))
                    logger.warning("Ozon rate limited (429), waiting %d sec", retry_after)
                    await asyncio.sleep(retry_after)
                    continue
                raise
            except Exception as e:
                logger.error("Ошибка при поиске Ozon '%s': %s", query, e)
                raise
        return []

    async def fetch_reviews(self, product_id: str) -> list[str]:
        """Получить отзывы на товар через публичный эндпоинт.

        Возвращает список текстов отзывов.
        """
        try:
            resp = await self._client.get(
                _OZON_PUBLIC_BASE,
                params={"url": f"/product/{product_id}/reviews"},
            )
            resp.raise_for_status()
            data = resp.json()

            widget_states = data.get("widgetStates", {})
            reviews = self._extract_reviews(widget_states)
            return reviews
        except Exception as e:
            logger.error("Ошибка при получении отзывов Ozon %s: %s", product_id, e)
            return []

    def _extract_product_from_widgets(
        self, widget_states: dict[str, Any], product_id: str
    ) -> dict[str, Any] | None:
        """Извлечь данные о товаре из widgetStates."""
        import json as _json

        for key, value in widget_states.items():
            if "webProductHeading" in key or "productHeading" in key:
                try:
                    parsed = _json.loads(value) if isinstance(value, str) else value
                    name = parsed.get("title", "")
                    if name:
                        # Ищем цену в других виджетах
                        price_data = self._find_price_widget(widget_states)
                        return {
                            "product_id": str(product_id),
                            "name": name,
                            "brand": parsed.get("brand", ""),
                            "price": price_data.get("price", 0),
                            "old_price": price_data.get("old_price", 0),
                            "discount": price_data.get("discount", 0),
                            "rating": price_data.get("rating", 0),
                            "feedbacks": price_data.get("feedbacks", 0),
                            "marketplace": "ozon",
                        }
                except (ValueError, TypeError):
                    continue
        return None

    def _find_price_widget(self, widget_states: dict[str, Any]) -> dict[str, Any]:
        """Найти виджет с ценой в widgetStates."""
        import json as _json

        result: dict[str, Any] = {"price": 0, "old_price": 0, "discount": 0, "rating": 0, "feedbacks": 0}

        for key, value in widget_states.items():
            if "webPrice" in key or "Price" in key:
                try:
                    parsed = _json.loads(value) if isinstance(value, str) else value
                    # Пробуем разные форматы цены
                    price_str = parsed.get("price", "") or parsed.get("cardPrice", "")
                    if isinstance(price_str, str):
                        price_str = price_str.replace("\u2009", "").replace(" ", "").replace("\u20bd", "")
                        try:
                            result["price"] = float(price_str)
                        except ValueError:
                            pass
                    elif isinstance(price_str, (int, float)):
                        result["price"] = float(price_str)

                    old_str = parsed.get("originalPrice", "") or parsed.get("basePrice", "")
                    if isinstance(old_str, str):
                        old_str = old_str.replace("\u2009", "").replace(" ", "").replace("\u20bd", "")
                        try:
                            result["old_price"] = float(old_str)
                        except ValueError:
                            pass
                    elif isinstance(old_str, (int, float)):
                        result["old_price"] = float(old_str)

                    if result["old_price"] > 0 and result["price"] > 0:
                        result["discount"] = round(
                            (1 - result["price"] / result["old_price"]) * 100
                        )
                    break
                except (ValueError, TypeError):
                    continue

        return result

    def _extract_search_results(
        self, widget_states: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        """Извлечь результаты поиска из widgetStates."""
        import json as _json

        results: list[dict[str, Any]] = []
        for key, value in widget_states.items():
            if "searchResultsV2" in key or "catalog" in key.lower():
                try:
                    parsed = _json.loads(value) if isinstance(value, str) else value
                    items = parsed.get("items", [])
                    for item in items[:limit]:
                        product = self._parse_search_item(item)
                        if product:
                            results.append(product)
                    if results:
                        break
                except (ValueError, TypeError):
                    continue
        return results[:limit]

    @staticmethod
    def _parse_search_item(item: dict[str, Any]) -> dict[str, Any] | None:
        """Распарсить элемент результатов поиска."""
        try:
            main_state = item.get("mainState", [])
            name = ""
            price = 0.0
            old_price = 0.0

            for atom in main_state:
                atom_type = atom.get("atom", {}).get("type", "")
                if atom_type == "textAtom" and not name:
                    name = atom.get("atom", {}).get("text", "")
                elif atom_type == "priceAtom":
                    price_text = atom.get("atom", {}).get("price", "")
                    if isinstance(price_text, str):
                        price_text = price_text.replace("\u2009", "").replace(" ", "").replace("\u20bd", "")
                        try:
                            price = float(price_text)
                        except ValueError:
                            pass

            product_id = str(item.get("id", item.get("cellTrackingInfo", {}).get("id", "")))

            discount = 0
            if old_price > 0 and price > 0:
                discount = round((1 - price / old_price) * 100)

            if not name and not product_id:
                return None

            return {
                "product_id": product_id,
                "name": name,
                "brand": "",
                "price": price,
                "old_price": old_price,
                "discount": discount,
                "rating": 0,
                "feedbacks": 0,
                "marketplace": "ozon",
            }
        except Exception:
            return None

    def _extract_reviews(self, widget_states: dict[str, Any]) -> list[str]:
        """Извлечь тексты отзывов из widgetStates."""
        import json as _json

        reviews: list[str] = []
        for key, value in widget_states.items():
            if "review" in key.lower():
                try:
                    parsed = _json.loads(value) if isinstance(value, str) else value
                    items = parsed.get("reviews", parsed.get("items", []))
                    for item in items:
                        text = ""
                        if isinstance(item, dict):
                            text = item.get("text", "") or item.get("comment", "")
                            if isinstance(text, dict):
                                text = text.get("text", "")
                        if text and isinstance(text, str):
                            reviews.append(text.strip())
                except (ValueError, TypeError):
                    continue
        return reviews

    @staticmethod
    def _parse_seo_data(seo: dict[str, Any], product_id: str) -> dict[str, Any] | None:
        """Извлечь базовые данные из SEO-секции ответа."""
        title = seo.get("title", "")
        if not title:
            return None
        return {
            "product_id": str(product_id),
            "name": title,
            "brand": "",
            "price": 0,
            "old_price": 0,
            "discount": 0,
            "rating": 0,
            "feedbacks": 0,
            "marketplace": "ozon",
        }
