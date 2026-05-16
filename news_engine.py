"""Новостной модуль: заголовки для контекста ИИ-аналитика.

Обращаемся к NewsAPI (https://newsapi.org/v2/everything) через aiohttp.
При любой ошибке возвращаем пустой список и пишем предупреждение по-русски,
чтобы торговый цикл не падал.
"""

from __future__ import annotations

import collections
import re
from typing import Any

import aiohttp

import config


# --- News dedup ----------------------------------------------------------

# Кольцевая история нормализованных заголовков для cross-call дедупа.
# Делает невидимыми "копии новости" из разных source - они приходят на
# первой минуте после события и могут раздуть промпт макро-сентинелу
# до бессмысленных размеров (10 одинаковых заголовков о CPI - ноль
# полезного сигнала, расход токенов x10).
_RECENT_TITLE_HASHES: collections.deque = collections.deque(maxlen=200)
_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)


def _normalize_title(title: str) -> str:
    """Нормализованный ключ заголовка для дедупа.

    Убираем пунктуацию, нижний регистр, схлопываем пробелы. Это даёт
    устойчивый ключ для одинаковых формулировок типа:
      "Fed holds rates steady"  vs  "Fed holds rates steady."
      "Fed Holds Rates Steady"  vs  "Fed   holds  rates steady"
    """
    if not title:
        return ""
    s = str(title).strip().lower()
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def dedup_titles(titles: list[str]) -> list[str]:
    """Вернуть подмножество titles без дублей среди (а) самих titles,
    (б) недавно показанных нам заголовков (последние 200).
    Сохраняет порядок входа. Пустые заголовки опускает."""
    out: list[str] = []
    seen_in_call: set[str] = set()
    for t in titles or []:
        key = _normalize_title(t)
        if not key:
            continue
        if key in seen_in_call:
            continue
        if key in _RECENT_TITLE_HASHES:
            continue
        seen_in_call.add(key)
        _RECENT_TITLE_HASHES.append(key)
        out.append(str(t).strip())
    return out


async def fetch_headlines(
    session: aiohttp.ClientSession,
    query: str = "(crypto OR bitcoin OR fed)",
    page_size: int = 10,
    timeout: int = 15,
) -> list[str]:
    """Получить до `page_size` свежих заголовков по теме.
    Возвращает список строк (title). На любой ошибке - пустой список.

    page_size жёстко ограничиваем диапазоном [1, 100] - NewsAPI отвергает
    значения больше 100 (возвращает parameterInvalid).
    """
    if not config.NEWS_API_KEY:
        print("[NEWS] NEWS_API_KEY не задан - пропускаем получение заголовков")
        return []

    try:
        clamped_page_size = max(1, min(int(page_size), 100))
    except (TypeError, ValueError):
        clamped_page_size = 10

    params = {
        "q": query,
        "language": "en",
        "pageSize": clamped_page_size,
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
    raw_titles: list[str] = []
    for art in articles[:clamped_page_size]:
        title = (art.get("title") or "").strip()
        if title:
            raw_titles.append(title)

    # Дедуп по нормализованному ключу (cross-call, последние 200 заголовков).
    deduped = dedup_titles(raw_titles)
    skipped = len(raw_titles) - len(deduped)
    if skipped > 0:
        print(f"[NEWS] Дедуп: пропущено {skipped} дублей из {len(raw_titles)} заголовков")
    return deduped
