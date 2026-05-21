"""SEO meta tag generator using OpenAI."""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level reusable HTTP client for OpenAI API calls
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Get or create a module-level httpx.AsyncClient."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


class SEOGenerator:
    """Generates SEO-optimized meta tags for product pages."""

    async def generate_meta(self, product_name: str, category: str, price: float) -> dict:
        """Generate SEO meta tags for a product.

        Returns dict with keys: title, description, keywords.
        Falls back to template-based generation if API is unavailable.
        """
        if not settings.openai_api_key:
            return self._template_fallback(product_name, category, price)

        prompt = (
            f"Generate SEO meta tags for a product page.\n"
            f"Product: {product_name}\n"
            f"Category: {category}\n"
            f"Price: {price} RUB\n\n"
            f"Reply in JSON format with keys: title (max 60 chars), "
            f"description (max 160 chars), keywords (comma-separated, max 10 keywords).\n"
            f"All text must be in Russian."
        )

        try:
            client = _get_http_client()
            resp = await client.post(
                f"{settings.openai_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.5,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                # Try to parse JSON from response
                import json

                # Strip markdown code fences if present
                if content.startswith("```"):
                    content = content.split("\n", 1)[1].rsplit("```", 1)[0]
                parsed = json.loads(content)
                return {
                    "title": parsed.get("title", product_name),
                    "description": parsed.get("description", ""),
                    "keywords": parsed.get("keywords", category),
                }
        except Exception as e:
            logger.error("SEO generation error: %s", e)

        return self._template_fallback(product_name, category, price)

    def _template_fallback(self, product_name: str, category: str, price: float) -> dict:
        """Generate basic SEO tags from templates when API is unavailable."""
        return {
            "title": f"Купить {product_name} - лучшая цена {price:.0f} руб.",
            "description": (
                f"{product_name} в категории {category}. "
                f"Актуальная цена {price:.0f} руб. "
                f"Сравнение цен на маркетплейсах, история изменений."
            ),
            "keywords": f"{product_name}, {category}, купить, цена, скидка, маркетплейс",
        }


seo_generator = SEOGenerator()
