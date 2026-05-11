"""Новостной модуль: заголовки для контекста ИИ-аналитика.

Обращаемся к NewsAPI (https://newsapi.org/v2/everything) через aiohttp.
При любой ошибке возвращаем пустой список и пишем предупреждение по-русски,
чтобы торговый цикл не падал.
"""

from __future__ import annotations

from typing import Any

import aiohttp

import config


async def fetch_headlines(
    session: aiohttp.ClientSession,
    query: str = "(crypto OR bitcoin OR fed)",
    page_size: int = 10,
    timeout: int = 15,
) -> list[str]:
    """Получить до `page_size` свежих заголовков по теме.
    Возвращает список строк (title). На любой ошибке - пустой список."""
    if not config.NEWS_API_KEY:
        print("[NEWS] NEWS_API_KEY не задан - пропускаем получение заголовков")
        return []

    params = {
        "q": query,
        "language": "en",
        "pageSize": page_size,
        "sortBy": "publishedAt",
    }
    headers = {"X-Api-Key": config.NEWS_API_KEY}

    try:
        async with session.get(
            config.NEWS_API_URL, params=params, headers=headers, timeout=timeout
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                print(f"[NEWS] NewsAPI вернул статус {resp.status}: {body[:200]}")
                return []
            data: dict[str, Any] = await resp.json()
    except aiohttp.ClientError as exc:
        print(f"[NEWS] Сетевая ошибка NewsAPI: {exc}")
        return []
    except Exception as exc:  # noqa: BLE001
        print(f"[NEWS] Неожиданная ошибка NewsAPI: {exc}")
        return []

    if data.get("status") != "ok":
        print(f"[NEWS] NewsAPI ответил со статусом: {data.get('status')}")
        return []

    articles = data.get("articles") or []
    titles: list[str] = []
    for art in articles[:page_size]:
        title = (art.get("title") or "").strip()
        if title:
            titles.append(title)
    return titles
