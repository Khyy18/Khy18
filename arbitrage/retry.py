"""Асинхронный retry-хелпер с экспоненциальным backoff.

Используется для HTTP-запросов к внешним API (OddsAPI, Pinnacle, Betfair).
- HTTP 429: ждём Retry-After или 60 секунд, повторяем
- HTTP 5xx: экспоненциальный backoff (1s, 2s, 4s), повторяем
- HTTP 4xx (кроме 429): ошибка немедленно, без повтора
- HTTP 2xx: возвращаем ответ
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)


async def retry_request(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    max_retries: int = 3,
    backoff_base: float = 1.0,
    **kwargs: Any,
) -> aiohttp.ClientResponse:
    """Выполняет HTTP-запрос с retry и экспоненциальным backoff.

    Args:
        session: aiohttp-сессия
        method: HTTP-метод ('GET' или 'POST')
        url: URL запроса
        max_retries: максимальное количество повторов
        backoff_base: базовое время ожидания для backoff (секунды)
        **kwargs: дополнительные параметры для session.request()

    Returns:
        aiohttp.ClientResponse - ответ сервера

    Raises:
        aiohttp.ClientResponseError: при 4xx ошибке (кроме 429) или исчерпании попыток
    """
    last_exc: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            resp = await session.request(method, url, **kwargs)

            status = resp.status

            # Успех
            if 200 <= status < 300:
                return resp

            # 429 Too Many Requests
            if status == 429:
                retry_after_hdr = resp.headers.get("Retry-After")
                if retry_after_hdr is not None:
                    try:
                        wait_time = float(retry_after_hdr)
                    except (ValueError, TypeError):
                        wait_time = 60.0
                else:
                    wait_time = 60.0
                logger.warning(
                    "HTTP 429 на %s, ожидание %.1f сек (попытка %d/%d)",
                    url, wait_time, attempt + 1, max_retries + 1,
                )
                if attempt < max_retries:
                    await asyncio.sleep(wait_time)
                    continue
                return resp

            # 5xx Server Error
            if status >= 500:
                wait_time = backoff_base * (2 ** attempt)
                logger.warning(
                    "HTTP %d на %s, backoff %.1f сек (попытка %d/%d)",
                    status, url, wait_time, attempt + 1, max_retries + 1,
                )
                if attempt < max_retries:
                    await asyncio.sleep(wait_time)
                    continue
                return resp

            # 4xx (кроме 429) - не повторяем
            return resp

        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last_exc = exc
            if attempt < max_retries:
                wait_time = backoff_base * (2 ** attempt)
                logger.warning(
                    "Ошибка соединения %s: %s, backoff %.1f сек (попытка %d/%d)",
                    url, exc, wait_time, attempt + 1, max_retries + 1,
                )
                await asyncio.sleep(wait_time)
                continue
            raise

    # Не должны сюда попасть, но на всякий случай
    if last_exc is not None:
        raise last_exc
    raise aiohttp.ClientError(f"Retry exhausted for {url}")
