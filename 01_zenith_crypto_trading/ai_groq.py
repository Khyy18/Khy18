"""Тонкий shim поверх ai_router.LLMRouter.

Изначально модуль ходил напрямую в Groq. Теперь все ИИ-вызовы (macro,
regime, postmortem, объяснение отклонений) идут через единый роутер,
который перебирает Groq -> Cerebras -> Gemini с circuit-breaker 120с.

Чтобы не править ai_macro_sentinel/ai_regime/ai_postmortem (а они все
импортируют ai_groq.call_groq_json / call_groq_text), оставляем здесь
старое API; внутри делегируем в ai_router.

Также сохраняются publicly-importable хелперы parse_model_json и
extract_text - они всё ещё могут пригодиться внешним вызывающим (например,
тестам или скриптам, которые принимают raw ответы Groq).
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import aiohttp

import ai_router


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_BARE_JSON_RE = re.compile(r"(\{[\s\S]*\})")


def parse_model_json(text: str) -> Optional[dict[str, Any]]:
    """Толерантный парс JSON-ответа модели (legacy helper)."""
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
    """Достать текст из OpenAI-совместимого ответа (legacy helper)."""
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
        print(f"[GROQ] Не удалось извлечь текст: {exc}")
        return ""


async def call_groq_json(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    max_output_tokens: int = 256,
    temperature: float = 0.2,
    timeout: int = 25,
) -> Optional[dict[str, Any]]:
    """Запросить структурированный JSON через роутер (Groq -> Cerebras -> Gemini)."""
    return await ai_router.call_llm_json(
        session,
        prompt,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        timeout=timeout,
    )


async def call_groq_text(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    max_output_tokens: int = 512,
    temperature: float = 0.3,
    timeout: int = 25,
) -> str:
    """Запросить свободный текст через роутер (Groq -> Cerebras -> Gemini)."""
    return await ai_router.call_llm_text(
        session,
        prompt,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        timeout=timeout,
    )
