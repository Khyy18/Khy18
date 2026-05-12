"""Общий помощник работы с Groq Inference API (OpenAI-совместимым).

Все ИИ-модули Zenith-Control Ultimate (macro-sentinel, regime-classifier,
post-mortem, объяснение отклонений) ходят в Groq через этот модуль.

Почему Groq, а не Gemini:
  - Бесплатная квота: 14400 RPD / 30 RPM против 20-1000 RPD у Gemini free.
    Для текущего паттерна (~50 вызовов/сутки) запаса хватает с огромным
    избытком, fallback-провайдер не нужен.
  - Скорость: модель llama-3.3-70b-versatile отвечает за 0.3-0.8 сек
    против 2-4 сек у Gemini Flash.
  - OpenAI-совместимый endpoint - стандартный JSON-формат messages.
  - response_format=json_object даёт гарантированно валидный JSON без
    markdown-обёрток (но fallback-парсер всё равно держим).

Ключевые правила:
  - API-ключ передаём ТОЛЬКО через заголовок Authorization: Bearer.
  - Никакого глобального состояния и сетевых вызовов на уровне модуля.
  - Любая ошибка - сетевая, парс, статус != 200 - молча логируется
    по-русски и наружу возвращается None (для JSON) или '' (для текста).
    Верхний слой сам решает fail-open/fail-closed политику.

Публичные функции:
  call_groq_json(session, prompt, **kwargs) -> Optional[dict]
  call_groq_text(session, prompt, **kwargs) -> str
  parse_model_json(text) -> Optional[dict]
  extract_text(data) -> str
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional

import aiohttp

import config


# Экспоненциальный backoff для Groq HTTP 429 (rate limit exceeded).
# На free-tier 14400 RPD / 30 RPM - 429 встречается крайне редко, но
# на всякий случай обрабатываем так же, как и для Gemini: 10 -> 20 -> 40с.
_GROQ_429_RETRIES = 3
_GROQ_429_BASE_SLEEP = 10


# Регулярки для устойчивого извлечения JSON из ответа модели.
# При response_format=json_object Groq возвращает чистый JSON, но оставляем
# fallback на случай если модель всё-таки обернёт его в fence или префикс.
_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_BARE_JSON_RE = re.compile(r"(\{[\s\S]*\})")


def parse_model_json(text: str) -> Optional[dict[str, Any]]:
    """Извлечь JSON из произвольного текста Groq.

    Порядок попыток:
      1) Сразу json.loads(text) - обычный путь при response_format=json_object.
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
    """Собрать строку из поля choices[0].message.content.

    Формат ответа Groq (OpenAI-совместимый):
      {"choices": [{"message": {"role": "assistant", "content": "..."}, ...}], ...}
    """
    try:
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content")
        if content is None:
            return ""
        return str(content).strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[GROQ] Не удалось извлечь текст из ответа: {exc}")
        return ""


def _headers() -> dict[str, str]:
    """Заголовки запроса. Ключ строго в Authorization: Bearer."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
    }


def _build_body(
    prompt: str,
    *,
    response_format_json: bool,
    max_output_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": config.GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": float(temperature),
        "max_tokens": int(max_output_tokens),
    }
    if response_format_json:
        # response_format=json_object просит модель вернуть валидный JSON без
        # markdown-обёртки. Для llama-3.3-70b-versatile это работает надёжно.
        body["response_format"] = {"type": "json_object"}
    return body


async def _post(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    response_format_json: bool,
    max_output_tokens: int,
    temperature: float,
    timeout: int,
) -> Optional[dict[str, Any]]:
    """Низкоуровневый POST в Groq. Возвращает raw dict или None."""
    if not config.GROQ_API_KEY:
        print("[GROQ] GROQ_API_KEY пуст - вызов пропущен")
        return None

    body = _build_body(
        prompt,
        response_format_json=response_format_json,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
    )
    body_bytes = json.dumps(body, ensure_ascii=False)

    for attempt in range(_GROQ_429_RETRIES):
        try:
            async with session.post(
                config.GROQ_URL,
                data=body_bytes,
                headers=_headers(),
                timeout=timeout,
            ) as resp:
                if resp.status == 429:
                    # Rate limit. Экспоненциальный backoff: 10 -> 20 -> 40с.
                    body_text = await resp.text()
                    is_last = attempt == _GROQ_429_RETRIES - 1
                    print(
                        f"[GROQ] HTTP 429 (попытка {attempt + 1}/"
                        f"{_GROQ_429_RETRIES}): {body_text[:160]}"
                    )
                    if is_last:
                        return None
                    delay = _GROQ_429_BASE_SLEEP * (2 ** attempt)
                    print(f"[GROQ] backoff {delay}с перед повтором")
                    await asyncio.sleep(delay)
                    continue
                if resp.status != 200:
                    body_text = await resp.text()
                    print(
                        "[GROQ] HTTP "
                        f"{resp.status}: {body_text[:200]}"
                    )
                    return None
                try:
                    return await resp.json()
                except (aiohttp.ContentTypeError, json.JSONDecodeError) as exc:
                    print(f"[GROQ] Не удалось распарсить JSON ответа: {exc}")
                    return None
        except aiohttp.ClientError as exc:
            print(f"[GROQ] Сетевая ошибка: {exc}")
            return None
        except Exception as exc:  # noqa: BLE001
            print(f"[GROQ] Неожиданная ошибка вызова: {exc}")
            return None
    return None


async def call_groq_json(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    max_output_tokens: int = 256,
    temperature: float = 0.2,
    timeout: int = 25,
) -> Optional[dict[str, Any]]:
    """Запросить у Groq структурированный JSON-ответ.

    Использует response_format=json_object - модель обязана вернуть валидный
    JSON. На любую ошибку возвращает None - верхний слой применяет свою
    политику (fail-open для режимного классификатора, fail-closed для
    входного гейта).
    """
    data = await _post(
        session,
        prompt,
        response_format_json=True,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        timeout=timeout,
    )
    if not data:
        return None
    text = extract_text(data)
    if not text:
        print("[GROQ] Пустой текст в ответе")
        return None
    parsed = parse_model_json(text)
    if parsed is None:
        print(f"[GROQ] Ответ не распарсился как JSON: {text[:200]}")
        return None
    return parsed


async def call_groq_text(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    max_output_tokens: int = 512,
    temperature: float = 0.3,
    timeout: int = 25,
) -> str:
    """Запросить у Groq свободный текст (без JSON-формата).

    На любую ошибку возвращает пустую строку.
    """
    data = await _post(
        session,
        prompt,
        response_format_json=False,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        timeout=timeout,
    )
    if not data:
        return ""
    return extract_text(data)
