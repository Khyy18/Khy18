"""Vision AI - product category classification from image."""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class VisionClassifier:
    """Classifies product category using OpenAI Vision API."""

    CATEGORIES = [
        "Электроника", "Одежда", "Обувь", "Красота", "Дом и сад",
        "Спорт", "Детские товары", "Продукты", "Авто", "Книги",
    ]

    async def classify_product(self, image_url: str) -> str:
        """Determine product category from image URL via OpenAI Vision.

        Returns category string or 'Другое' on failure.
        """
        if not settings.openai_api_key:
            return "Другое"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{settings.openai_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": (
                                            f"Classify this product into one of these categories: "
                                            f"{', '.join(self.CATEGORIES)}. "
                                            f"Reply with just the category name."
                                        ),
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": image_url},
                                    },
                                ],
                            }
                        ],
                        "max_tokens": 50,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    category = data["choices"][0]["message"]["content"].strip()
                    if category in self.CATEGORIES:
                        return category
                    return "Другое"
        except Exception as e:
            logger.error("Vision classification error: %s", e)
        return "Другое"


vision_classifier = VisionClassifier()
