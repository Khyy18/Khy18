"""Макро-сентинел: решает, нужно ли встать в blackout перед крупным макрорелизом.

Забирает свежие заголовки из NewsAPI и спрашивает у Groq строгий JSON:
  {"blackout": true|false, "until_utc": "...ISO8601..."|null, "reason": "..."}

Политика отказоустойчивости - **fail-OPEN**: при любой ошибке (сеть, парс,
отсутствие ключа) возвращаем blackout=False и громко предупреждаем по-русски.
Считаем, что пропустить макро-событие - меньшее зло, чем замкнуть бота на
сбоях внешних сервисов (у нас есть ещё ATR-стопы, режимный классификатор
и kill-switch по просадке).

Результат кэшируется модульно на config.AI_BLACKOUT_TTL_SEC секунд, чтобы
не бить по Groq каждую минуту.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp

import ai_groq
import config
import news_engine


_CACHE: dict[str, Any] = {"ts_epoch": 0.0, "value": None}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def clear_cache() -> None:
    """Сбросить модульный кэш (принудительный перезапрос при следующем check)."""
    _CACHE["ts_epoch"] = 0.0
    _CACHE["value"] = None


def _fail_open(reason: str) -> dict[str, Any]:
    """Сформировать fail-open ответ, одновременно записав его в кэш."""
    value = {
        "blackout": False,
        "until_utc": None,
        "reason": reason,
        "ts": _now_iso(),
    }
    _CACHE["ts_epoch"] = time.time()
    _CACHE["value"] = value
    return value


def _build_prompt(headlines: list[str]) -> str:
    lines = []
    for i, h in enumerate(headlines[:20], start=1):
        h_clean = str(h or "").strip().replace("\n", " ")
        if h_clean:
            lines.append(f"{i}. {h_clean}")
    headlines_block = "\n".join(lines) if lines else "(нет свежих заголовков)"
    return (
        "Ты макро-сентинел. Посмотри на заголовки и скажи, не предстоит ли "
        "в ближайшие 6 часов крупный макроэкономический релиз (FOMC, CPI, "
        "NFP, PPI, GDP, заседание ЦБ). Ответь СТРОГО одним JSON-объектом: "
        "{\"blackout\": true|false, \"until_utc\": \"ISO8601 в UTC\" или null, "
        "\"reason\": \"краткая причина\"}. Без комментариев.\n\n"
        f"Заголовки:\n{headlines_block}\n"
    )


async def check(session: aiohttp.ClientSession) -> dict[str, Any]:
    """Вернуть текущее решение по blackout. Кэш TTL = AI_BLACKOUT_TTL_SEC."""
    try:
        ttl = float(getattr(config, "AI_BLACKOUT_TTL_SEC", 0) or 0)
        if (
            _CACHE["value"] is not None
            and (time.time() - float(_CACHE["ts_epoch"])) < ttl
        ):
            return dict(_CACHE["value"])
    except Exception as exc:  # noqa: BLE001
        print(f"[MACRO] Сбой чтения кэша: {exc}")

    try:
        headlines = await news_engine.fetch_headlines(
            session,
            query=(
                "(FOMC OR CPI OR NFP OR ECB OR BoJ OR inflation OR "
                "\"jobs report\")"
            ),
            page_size=20,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[MACRO] Ошибка получения заголовков: {exc}")
        return _fail_open("Ошибка макро-сентинела, blackout не активирован")

    prompt = _build_prompt(headlines or [])

    try:
        parsed: Optional[dict[str, Any]] = await ai_groq.call_groq_json(
            session, prompt
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[MACRO] Ошибка вызова Groq: {exc}")
        return _fail_open("Ошибка макро-сентинела, blackout не активирован")

    if not isinstance(parsed, dict):
        print("[MACRO] Groq не вернул валидный JSON - fail-open")
        return _fail_open("Ошибка макро-сентинела, blackout не активирован")

    try:
        blackout = bool(parsed.get("blackout"))
        until_raw = parsed.get("until_utc")
        until_utc: Optional[str]
        if until_raw in (None, "", "null"):
            until_utc = None
        else:
            until_utc = str(until_raw)
        reason = str(parsed.get("reason", "") or "").strip()[:200]
        if not reason:
            reason = "без пояснения"
    except Exception as exc:  # noqa: BLE001
        print(f"[MACRO] Ошибка нормализации ответа Groq: {exc}")
        return _fail_open("Ошибка макро-сентинела, blackout не активирован")

    value = {
        "blackout": blackout,
        "until_utc": until_utc,
        "reason": reason,
        "ts": _now_iso(),
    }
    _CACHE["ts_epoch"] = time.time()
    _CACHE["value"] = value
    return dict(value)
