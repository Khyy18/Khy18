"""Хранилище портфолио и подбор релевантных работ.

Простое хранение работ портфолио с поиском по ключевым словам
для подбора наиболее подходящих примеров под конкретный заказ.
"""

from __future__ import annotations

from freelance_automation.base import Order

# Портфолио: список работ с метаданными
PORTFOLIO_ITEMS: list[dict] = [
    {
        "title": "Telegram-бот для автоматизации продаж",
        "description": "Разработка бота с интеграцией платежей и CRM",
        "tags": ["telegram", "bot", "python", "asyncio", "payments", "crm"],
        "url": "https://portfolio.example.com/telegram-bot",
    },
    {
        "title": "Парсер маркетплейсов",
        "description": "Сбор данных с Wildberries, Ozon с обходом защиты",
        "tags": ["parsing", "scraping", "python", "playwright", "wildberries", "ozon"],
        "url": "https://portfolio.example.com/marketplace-parser",
    },
    {
        "title": "Система A/B-тестирования рекламы",
        "description": "Движок сплит-тестов с Thompson Sampling и аналитикой",
        "tags": ["analytics", "ab-testing", "statistics", "python", "advertising"],
        "url": "https://portfolio.example.com/ab-testing",
    },
    {
        "title": "Криптовалютный торговый бот",
        "description": "Автоматическая торговля с AI-анализом рынка",
        "tags": ["crypto", "trading", "bot", "ai", "python", "asyncio"],
        "url": "https://portfolio.example.com/crypto-bot",
    },
    {
        "title": "Веб-приложение на FastAPI",
        "description": "REST API с авторизацией, PostgreSQL, Redis кешем",
        "tags": ["fastapi", "web", "api", "python", "postgresql", "redis"],
        "url": "https://portfolio.example.com/fastapi-app",
    },
]


def select_relevant(order: Order, top_k: int = 3) -> list[str]:
    """Подобрать наиболее релевантные работы из портфолио.

    Сопоставляет ключевые слова из заголовка и описания заказа
    с тегами портфолио. Возвращает описания top_k лучших совпадений.

    Args:
        order: Заказ для поиска релевантных работ.
        top_k: Максимальное количество возвращаемых работ.

    Returns:
        Список строк-описаний релевантных работ.
    """
    order_text = f"{order.title} {order.description}".lower()

    scored: list[tuple[int, dict]] = []
    for item in PORTFOLIO_ITEMS:
        score = sum(1 for tag in item["tags"] if tag.lower() in order_text)
        scored.append((score, item))

    # Сортировка по релевантности (убывание), затем берем top_k
    scored.sort(key=lambda x: x[0], reverse=True)

    results: list[str] = []
    for score, item in scored[:top_k]:
        if score > 0:
            results.append(f"{item['title']} - {item['description']} ({item['url']})")

    return results
