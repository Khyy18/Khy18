"""LLMRouter: единая точка вызова LLM с провайдерным fallback и circuit-breaker.

Цепочка провайдеров (от дешёвого/быстрого к запасному):
  1. Groq      - llama-3.3-70b-versatile, 14400 RPD / 30 RPM (основной)
  2. Cerebras  - llama-3.3-70b, 14400 RPD (резервный, OpenAI-совместимый API)
  3. Gemini    - gemini-2.0-flash, 1500 RPD (последний рубеж)

Circuit-breaker:
  - 3 подряд ошибки на провайдере (HTTP 5xx, timeout, парс) -> провайдер
    помечается OPEN, его пропускаем при следующих вызовах.
  - Через CIRCUIT_BREAKER_RESET_SEC = 120 секунд провайдер автоматически
    переводится в HALF_OPEN: один пробный запрос, при успехе - CLOSED.
  - HTTP 429 (rate limit) НЕ считается ошибкой провайдера: переходим к
    следующему провайдеру в цепочке без увеличения счётчика.

Публичный API:
  call_llm_json(session, prompt, **kwargs)  -> Optional[dict]
  call_llm_text(session, prompt, **kwargs)  -> str
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Optional

import aiohttp

import config


CIRCUIT_BREAKER_THRESHOLD = 3      # подряд ошибок -> open
CIRCUIT_BREAKER_RESET_SEC = 120    # через сколько секунд пробуем half-open

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_BARE_JSON_RE = re.compile(r"(\{[\s\S]*\})")


def _parse_json(text: str) -> Optional[dict[str, Any]]:
    """Толерантный парс JSON из произвольного текста LLM."""
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


# --- Базовый класс провайдера ---------------------------------------------

class _Provider:
    """Базовый класс провайдера."""

    name: str = ""
    enabled_attr: str = ""  # имя атрибута config с API-ключом

    _consecutive_errors: int = 0
    _opened_at_epoch: float = 0.0

    def __init__(self) -> None:
        self._consecutive_errors = 0
        self._opened_at_epoch = 0.0

    @property
    def is_configured(self) -> bool:
        """True, если в config задан непустой ключ."""
        return bool(getattr(config, self.enabled_attr, "") or "")

    @property
    def state(self) -> str:
        """CLOSED / OPEN / HALF_OPEN."""
        if self._consecutive_errors < CIRCUIT_BREAKER_THRESHOLD:
            return "CLOSED"
        elapsed = time.time() - self._opened_at_epoch
        if elapsed >= CIRCUIT_BREAKER_RESET_SEC:
            return "HALF_OPEN"
        return "OPEN"

    def _record_success(self) -> None:
        self._consecutive_errors = 0
        self._opened_at_epoch = 0.0

    def _record_error(self) -> None:
        self._consecutive_errors += 1
        if self._consecutive_errors == CIRCUIT_BREAKER_THRESHOLD:
            self._opened_at_epoch = time.time()

    async def call(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        *,
        response_format_json: bool,
        max_output_tokens: int,
        temperature: float,
        timeout: int,
    ) -> Optional[str]:
        raise NotImplementedError


# --- Groq -----------------------------------------------------------------

class _GroqProvider(_Provider):
    name = "groq"
    enabled_attr = "GROQ_API_KEY"

    async def call(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        *,
        response_format_json: bool,
        max_output_tokens: int,
        temperature: float,
        timeout: int,
    ) -> Optional[str]:
        body: dict[str, Any] = {
            "model": getattr(config, "GROQ_MODEL", "llama-3.3-70b-versatile"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(temperature),
            "max_tokens": int(max_output_tokens),
        }
        if response_format_json:
            body["response_format"] = {"type": "json_object"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.GROQ_API_KEY}",
        }
        try:
            async with session.post(
                config.GROQ_URL,
                data=json.dumps(body, ensure_ascii=False),
                headers=headers,
                timeout=timeout,
            ) as resp:
                if resp.status == 429:
                    return None
                if resp.status != 200:
                    self._record_error()
                    return None
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            self._record_error()
            return None
        except Exception:  # noqa: BLE001
            self._record_error()
            return None

        try:
            choices = data.get("choices") or []
            if not choices:
                self._record_error()
                return None
            content = (choices[0].get("message") or {}).get("content")
            if content is None:
                self._record_error()
                return None
            text = str(content).strip()
        except Exception:  # noqa: BLE001
            self._record_error()
            return None

        self._record_success()
        return text


# --- Cerebras (OpenAI-совместимый) ----------------------------------------

class _CerebrasProvider(_Provider):
    name = "cerebras"
    enabled_attr = "CEREBRAS_API_KEY"

    async def call(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        *,
        response_format_json: bool,
        max_output_tokens: int,
        temperature: float,
        timeout: int,
    ) -> Optional[str]:
        body: dict[str, Any] = {
            "model": getattr(config, "CEREBRAS_MODEL", "llama-3.3-70b"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(temperature),
            "max_tokens": int(max_output_tokens),
        }
        if response_format_json:
            body["response_format"] = {"type": "json_object"}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.CEREBRAS_API_KEY}",
        }
        url = getattr(
            config,
            "CEREBRAS_URL",
            "https://api.cerebras.ai/v1/chat/completions",
        )
        try:
            async with session.post(
                url,
                data=json.dumps(body, ensure_ascii=False),
                headers=headers,
                timeout=timeout,
            ) as resp:
                if resp.status == 429:
                    return None
                if resp.status != 200:
                    self._record_error()
                    return None
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            self._record_error()
            return None
        except Exception:  # noqa: BLE001
            self._record_error()
            return None

        try:
            choices = data.get("choices") or []
            if not choices:
                self._record_error()
                return None
            content = (choices[0].get("message") or {}).get("content")
            if content is None:
                self._record_error()
                return None
            text = str(content).strip()
        except Exception:  # noqa: BLE001
            self._record_error()
            return None

        self._record_success()
        return text


# --- Gemini ---------------------------------------------------------------

class _GeminiProvider(_Provider):
    name = "gemini"
    enabled_attr = "GEMINI_API_KEY"

    async def call(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        *,
        response_format_json: bool,
        max_output_tokens: int,
        temperature: float,
        timeout: int,
    ) -> Optional[str]:
        model = getattr(config, "GEMINI_MODEL", "gemini-2.0-flash")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:"
            f"generateContent?key={config.GEMINI_API_KEY}"
        )
        body: dict[str, Any] = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]},
            ],
            "generationConfig": {
                "temperature": float(temperature),
                "maxOutputTokens": int(max_output_tokens),
            },
        }
        if response_format_json:
            body["generationConfig"]["responseMimeType"] = "application/json"

        try:
            async with session.post(
                url,
                data=json.dumps(body, ensure_ascii=False),
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            ) as resp:
                if resp.status == 429:
                    return None
                if resp.status != 200:
                    self._record_error()
                    return None
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            self._record_error()
            return None
        except Exception:  # noqa: BLE001
            self._record_error()
            return None

        try:
            candidates = data.get("candidates") or []
            if not candidates:
                self._record_error()
                return None
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join(str(p.get("text", "")) for p in parts).strip()
            if not text:
                self._record_error()
                return None
        except Exception:  # noqa: BLE001
            self._record_error()
            return None

        self._record_success()
        return text


# --- Роутер ----------------------------------------------------------------

class LLMRouter:
    """Перебирает провайдеров в порядке цепочки. Уважает circuit-breaker."""

    def __init__(self) -> None:
        self.providers: list[_Provider] = [
            _GroqProvider(),
            _CerebrasProvider(),
            _GeminiProvider(),
        ]

    def status(self) -> list[dict[str, Any]]:
        """Снимок состояния роутера для диагностики."""
        out: list[dict[str, Any]] = []
        for p in self.providers:
            out.append(
                {
                    "name": p.name,
                    "configured": p.is_configured,
                    "state": p.state,
                    "errors": p._consecutive_errors,
                }
            )
        return out

    async def call_text(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        *,
        response_format_json: bool,
        max_output_tokens: int,
        temperature: float,
        timeout: int,
    ) -> Optional[str]:
        for provider in self.providers:
            if not provider.is_configured:
                continue
            if provider.state == "OPEN":
                continue
            text = await provider.call(
                session,
                prompt,
                response_format_json=response_format_json,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                timeout=timeout,
            )
            if text:
                return text
        return None


# Модульный синглтон.
_ROUTER: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = LLMRouter()
    return _ROUTER


# --- Публичные API ---------------------------------------------------------

async def call_llm_json(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    max_output_tokens: int = 256,
    temperature: float = 0.2,
    timeout: int = 25,
) -> Optional[dict[str, Any]]:
    """Спросить у LLM структурированный JSON (с fallback по цепочке)."""
    router = get_router()
    text = await router.call_text(
        session,
        prompt,
        response_format_json=True,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        timeout=timeout,
    )
    if not text:
        return None
    parsed = _parse_json(text)
    if parsed is None:
        return None
    return parsed


async def call_llm_text(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    max_output_tokens: int = 512,
    temperature: float = 0.3,
    timeout: int = 25,
) -> str:
    """Спросить у LLM свободный текст (с fallback по цепочке)."""
    router = get_router()
    text = await router.call_text(
        session,
        prompt,
        response_format_json=False,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        timeout=timeout,
    )
    return text or ""
