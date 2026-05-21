"""Ранжирование товаров по привлекательности скидки."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Веса факторов ранжирования
_WEIGHTS = {
    "discount_depth": 0.3,
    "brand_popularity": 0.2,
    "review_count": 0.15,
    "review_score": 0.15,
    "price_stability": 0.1,
    "category_demand": 0.1,
}

# Известные популярные бренды (для эвристики brand_popularity)
_POPULAR_BRANDS = {
    "samsung", "apple", "xiaomi", "huawei", "sony", "lg", "bosch",
    "philips", "dyson", "nike", "adidas", "puma", "lego", "hasbro",
    "tefal", "moulinex", "braun", "oral-b", "gillette", "loreal",
    "maybelline", "garnier", "nivea", "zara", "h&m", "uniqlo",
}

# Популярные категории
_POPULAR_CATEGORIES = {
    "электроника", "смартфоны", "ноутбуки", "бытовая техника",
    "одежда", "обувь", "красота", "здоровье", "детские товары",
    "спорт", "дом", "кухня", "игрушки",
}


class ProductRanker:
    """Ранжирование товаров по привлекательности для публикации."""

    async def rank_products(self, products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Ранжировать товары, добавив поле 'score' (0-100).

        Сортирует по убыванию score.
        """
        scored = []
        for product in products:
            score = self._calculate_score(product)
            product_copy = dict(product)
            product_copy["score"] = score
            scored.append(product_copy)

        scored.sort(key=lambda p: p["score"], reverse=True)
        return scored

    def _calculate_score(self, product: dict[str, Any]) -> int:
        """Рассчитать итоговый score по факторам."""
        scores: dict[str, float] = {}

        # Глубина скидки (0-100)
        discount = product.get("discount", 0)
        scores["discount_depth"] = min(discount / 80 * 100, 100)

        # Популярность бренда (0-100)
        brand = (product.get("brand") or "").lower()
        scores["brand_popularity"] = 80 if brand in _POPULAR_BRANDS else 30

        # Количество отзывов (0-100)
        feedbacks = product.get("feedbacks", 0)
        if feedbacks >= 1000:
            scores["review_count"] = 100
        elif feedbacks >= 100:
            scores["review_count"] = 70
        elif feedbacks >= 10:
            scores["review_count"] = 40
        else:
            scores["review_count"] = 10

        # Рейтинг (0-100)
        rating = product.get("rating", 0)
        scores["review_score"] = min(rating / 5.0 * 100, 100)

        # Стабильность цены (0-100) - если есть история
        price_history = product.get("price_history", [])
        if price_history and len(price_history) >= 3:
            avg = sum(price_history) / len(price_history)
            if avg > 0:
                variance = sum((p - avg) ** 2 for p in price_history) / len(price_history)
                relative_var = variance / (avg ** 2)
                # Чем меньше variance, тем стабильнее цена
                scores["price_stability"] = max(0, 100 - relative_var * 500)
            else:
                scores["price_stability"] = 50
        else:
            scores["price_stability"] = 50  # нет данных, среднее значение

        # Популярность категории (0-100)
        category = (product.get("category") or "").lower()
        if any(cat in category for cat in _POPULAR_CATEGORIES):
            scores["category_demand"] = 80
        else:
            scores["category_demand"] = 40

        # Взвешенная сумма
        total = sum(scores[k] * _WEIGHTS[k] for k in _WEIGHTS)
        return int(min(max(total, 0), 100))
