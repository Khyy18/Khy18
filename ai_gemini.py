"""Общий помощник работы с Google Gemini API.

Все ИИ-модули Zenith-Control Ultimate (macro-sentinel, regime-classifier,
post-mortem, объяснение отклонений) ходят в Gemini через этот модуль.

Ключевые правила:
  - API-ключ передаём ТОЛЬКО через заголовок `x-goog-api-key`.
    Никогда не используем key= в query-параметрах (это попадает в логи
    прокси и CDN).
  - Никакого глобального состояния и сетевых вызовов на уровне модуля.
  - Любая ошибка - сетевая, парс, статус != 200 - молча логируется
    по-русски и наружу возвращается None (для JSON) или '' (для текста).
    Верхний слой сам решает fail-open/fail-closed политику.

Публичные функции:
  call_gemini_json(session, prompt, **kwargs) -> Optional[dict]
  call_gemini_text(session, prompt, **kwargs) -> str
  parse_model_json(text) -> Optional[dict]
  extract_text(data) -> str
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import aiohttp

import config


# Регулярки для устойчивого извлечения JSON из ответа модели.
_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_BARE_JSON_RE = re.compile(r"(\{[\s\S]*\})")


def parse_model_json(text: str) -> Optional[dict[str, Any]]:
    """Извлечь JSON из произвольного текста Gemini.

    Порядок попыток:
      1) Сразу json.loads(text).
      2) Поиск блока ```json ... ``` и парс внутренностей.
      3) Голый {...} блок через жадный regex.
    Возвращает None, если ни один путь не дал валидный dict.
    """
    if not text:
        return None
    try:
        val = json.loads(text)
        if isinstance(val, dict):
            return val
    except json.JSONDecodeError:
        pass
    m = _FENCE_RE.search(text)
    if m:
        try:
            val = json.loads(m.group(1))
            if isinstance(val, dict):
                return val
        except json.JSONDecodeError:
            pass
    m = _BARE_JSON_RE.search(text)
    if m:
        try:
            val = json.loads(m.group(1))
            if isinstance(val, dict):
                return val
        except json.JSONDecodeError:
            pass
    return None


def extract_text(data: dict[str, Any]) -> str:
    """Собрать строку из поля candidates[0].content.parts[*].text."""
    try:
        candidates = data.get("candidates") or []
        if not candidates:
            return ""
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts).strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[GEMINI] Не удалось извлечь текст из ответа: {exc}")
        return ""


def _headers() -> dict[str, str]:
    """Заголовки запроса. Ключ строго в x-goog-api-key, НЕ в URL."""
    return {
        "Content-Type": "application/json",
        "x-goog-api-key": config.GEMINI_API_KEY,
    }


def _build_generation_config(
    *,
    response_mime_type: Optional[str],
    max_output_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    gen: dict[str, Any] = {
        "temperature": float(temperature),
        "maxOutputTokens": int(max_output_tokens),
    }
    if response_mime_type:
        gen["responseMimeType"] = response_mime_type
    return gen


async def _post(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    response_mime_type: Optional[str],
    max_output_tokens: int,
    temperature: float,
    timeout: int,
) -> Optional[dict[str, Any]]:
    """Низкоуровневый POST в Gemini. Возвращает raw dict или None."""
    if not config.GEMINI_API_KEY:
        print("[GEMINI] GEMINI_API_KEY пуст - вызов пропущен")
        return None

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": _build_generation_config(
            response_mime_type=response_mime_type,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        ),
    }
    try:
        async with session.post(
            config.GEMINI_URL,
            data=json.dumps(body, ensure_ascii=False),
            headers=_headers(),
            timeout=timeout,
        ) as resp:
            if resp.status != 200:
                body_text = await resp.text()
                print(
                    "[GEMINI] HTTP "
                    f"{resp.status}: {body_text[:200]}"
                )
                return None
            try:
                return await resp.json()
            except (aiohttp.ContentTypeError, json.JSONDecodeError) as exc:
                print(f"[GEMINI] Не удалось распарсить JSON ответа: {exc}")
                return None
    except aiohttp.ClientError as exc:
        print(f"[GEMINI] Сетевая ошибка: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[GEMINI] Неожиданная ошибка вызова: {exc}")
        return None


async def call_gemini_json(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    response_mime_type: str = "application/json",
    max_output_tokens: int = 256,
    temperature: float = 0.2,
    timeout: int = 25,
) -> Optional[dict[str, Any]]:
    """Запросить у Gemini структурированный JSON-ответ.

    На любую ошибку возвращает None - верхний слой применяет свою политику
    (fail-open для режимного классификатора, fail-closed для входного гейта).
    """
    data = await _post(
        session,
        prompt,
        response_mime_type=response_mime_type,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        timeout=timeout,
    )
    if not data:
        return None
    text = extract_text(data)
    if not text:
        print("[GEMINI] Пустой текст в ответе")
        return None
    parsed = parse_model_json(text)
    if parsed is None:
        print(f"[GEMINI] Ответ не распарсился как JSON: {text[:200]}")
        return None
    return parsed


async def call_gemini_text(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    response_mime_type: Optional[str] = None,
    max_output_tokens: int = 512,
    temperature: float = 0.3,
    timeout: int = 25,
) -> str:
    """Запросить у Gemini свободный текст (без JSON-формата).

    На любую ошибку возвращает пустую строку.
    """
    data = await _post(
        session,
        prompt,
        response_mime_type=response_mime_type,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        timeout=timeout,
    )
    if not data:
        return ""
    return extract_text(data)
