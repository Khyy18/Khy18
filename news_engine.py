"""Новостной модуль: заголовки для контекста ИИ-аналитика.

Обращаемся к NewsAPI (https://newsapi.org/v2/everything) через aiohttp.
При любой ошибке возвращаем пустой список и пишем предупреждение по-русски,
чтобы торговый цикл не падал.
"""

from __future__ import annotations

import re
from typing import Any

import aiohttp

import config


# --- Дедупликация заголовков ----------------------------------------------

# Регулярки для нормализации заголовка перед хешированием:
# 1) убираем источник/кавычки/брекеты, "- CoinDesk", "[Reuters]" и т.п.;
# 2) сжимаем неалфавитное → пробел;
# 3) пробелы → один.
_SOURCE_TAIL_RE = re.compile(
    r"[\s\-—|·:]*\b(reuters|bloomberg|coindesk|cointelegraph|the block|"
    r"decrypt|forbes|cnbc|wsj|bbc|cnn|axios|theblock)\b.*$",
    re.IGNORECASE,
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9а-я]+", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def _normalize_title(title: str) -> str:
    """Привести заголовок к виду, по которому считаем дубли.

    Дубли — это один и тот же event с разными источниками или мелкими
    переформулировками. Стратегия:
      1) lower-case;
      2) убрать хвост вида "— Reuters", "| Bloomberg" и подобные;
      3) убрать любые символы кроме букв/цифр (в том числе кавычки, тире,
         emoji);
      4) collapse whitespace.
    Этого достаточно, чтобы CryptoPanic и NewsAPI с одной и той же новостью
    свернулись в одну строку, а перефразировки разных СМИ — в большинстве
    случаев тоже.
    """
    if not title:
        return ""
    s = str(title).lower().strip()
    s = _SOURCE_TAIL_RE.sub("", s)
    s = _NON_ALNUM_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def dedup_titles(titles: list[str]) -> list[str]:
    """Убрать дубли в списке заголовков с сохранением исходного порядка.

    Сравнение идёт по нормализованной форме (см. _normalize_title), на
    выход возвращаются ОРИГИНАЛЬНЫЕ строки — тот же текст, что показывает
    AI-Gate в prompt и Telegram. Пустые/нормализованные-в-пустоту
    строки выбрасываются.
    """
    seen: set[str] = set()
    out: list[str] = []
    for raw in titles or []:
        norm = _normalize_title(raw)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(str(raw).strip())
    return out


async def fetch_headlines(
    session: aiohttp.ClientSession,
    query: str = "(crypto OR bitcoin OR fed)",
    page_size: int = 10,
    timeout: int = 15,
) -> list[str]:
    """Получить до `page_size` свежих заголовков по теме.
    Возвращает список строк (title), уже без дубликатов. На любой ошибке -
    пустой список.

    page_size жёстко ограничиваем диапазоном [1, 100] - NewsAPI отвергает
    значения больше 100 (возвращает parameterInvalid). Дедупликация
    делается ПОСЛЕ запроса в NewsAPI и НЕ компенсирует уменьшение
    выборки — в редких случаях вернуть могут < page_size.
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
    titles: list[str] = []
    for art in articles[:clamped_page_size]:
        title = (art.get("title") or "").strip()
        if title:
            titles.append(title)
    deduped = dedup_titles(titles)
    if len(deduped) != len(titles):
        print(
            f"[NEWS] dedup: {len(titles)} → {len(deduped)} "
            f"(удалено {len(titles) - len(deduped)} дублей)"
        )
    return deduped
