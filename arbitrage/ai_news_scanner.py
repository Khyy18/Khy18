"""Сканер спортивных новостей с AI-анализом влияния.

Получает последние новости через NewsAPI и анализирует их влияние
на спортивные события через LLM.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Any, Optional

import aiohttp

from arbitrage import config

# Импорт ai_router из корневого проекта
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)
try:
    import ai_router
except ImportError:
    ai_router = None  # type: ignore

logger = logging.getLogger(__name__)

_NEWS_URL = (
    "https://newsapi.org/v2/everything"
    "?q=injury+OR+suspension+OR+lineup"
    "&language=en&sortBy=publishedAt&pageSize=10"
)


class NewsScanner:
    """Сканер новостей с LLM-оценкой влияния на спортивные события."""

    async def scan_news(self, session: aiohttp.ClientSession) -> list[dict[str, Any]]:
        """Получить и проанализировать последние спортивные новости.

        Returns:
            Список словарей с ключами:
              event_match, impact, magnitude, confidence, headline.
        """
        api_key = config.NEWS_API_KEY
        if not api_key:
            logger.debug("NEWS_API_KEY не задан, пропускаем сканирование новостей")
            return []

        url = f"{_NEWS_URL}&apiKey={api_key}"

        try:
            async with session.get(url, timeout=15) as resp:
                if resp.status != 200:
                    logger.warning("NewsAPI вернул статус %d", resp.status)
                    return []
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning("Ошибка запроса к NewsAPI: %s", exc)
            return []
        except Exception as exc:
            logger.warning("Неожиданная ошибка NewsAPI: %s", exc)
            return []

        articles = data.get("articles", [])
        if not articles:
            return []

        results: list[dict[str, Any]] = []
        for article in articles:
            title = str(article.get("title", "") or "")
            if not title:
                continue

            analysis = await self._analyze_headline(session, title)
            if analysis and analysis.get("confidence", 0) > 30:
                analysis["headline"] = title
                results.append(analysis)

        logger.info("NewsScanner: проанализировано %d статей, %d с влиянием", len(articles), len(results))
        return results

    async def _analyze_headline(
        self,
        session: aiohttp.ClientSession,
        headline: str,
    ) -> Optional[dict[str, Any]]:
        """Проанализировать заголовок через LLM."""
        if ai_router is None:
            return None

        prompt = (
            "Ты - эксперт по спортивным ставкам. Проанализируй новость и определи, "
            "повлияет ли она на какой-либо спортивный матч.\n\n"
            f"Заголовок: {headline}\n\n"
            "Если новость влияет на спортивное событие, ответь в JSON:\n"
            '{"event_match": "<команда или событие>", '
            '"impact": "positive"/"negative", '
            '"magnitude": <1-10 сила влияния>, '
            '"confidence": <0-100>}\n\n'
            "Если новость не связана со спортом или не влияет на матчи, ответь:\n"
            '{"event_match": "", "impact": "positive", "magnitude": 0, "confidence": 0}'
        )

        try:
            resp = await ai_router.call_llm_json(
                session,
                prompt,
                max_output_tokens=256,
                temperature=0.2,
                timeout=25,
            )
        except Exception as exc:
            logger.warning("Ошибка LLM в NewsScanner: %s", exc)
            return None

        if resp is None:
            return None

        event_match = str(resp.get("event_match", ""))
        impact = str(resp.get("impact", "positive"))
        if impact not in ("positive", "negative"):
            impact = "positive"

        magnitude = int(resp.get("magnitude", 0))
        magnitude = max(1, min(10, magnitude))

        confidence = int(resp.get("confidence", 0))
        confidence = max(0, min(100, confidence))

        return {
            "event_match": event_match,
            "impact": impact,
            "magnitude": magnitude,
            "confidence": confidence,
        }


async def news_scanner_loop(state: dict[str, Any], session: aiohttp.ClientSession) -> None:
    """Фоновый цикл сканирования новостей (каждые 600 секунд).

    Результаты сохраняются в state["news_findings"].
    """
    scanner = NewsScanner()
    interval = 600  # 10 минут

    while True:
        try:
            findings = await scanner.scan_news(session)
            state["news_findings"] = findings
            if findings:
                logger.info("news_scanner_loop: найдено %d новостей с влиянием", len(findings))
        except Exception as exc:
            logger.error("news_scanner_loop ошибка: %s", exc)

        await asyncio.sleep(interval)
