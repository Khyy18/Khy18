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
  - Состояние breaker'ов персистится в memory.kv_store, чтобы после
    рестарта мы не лезли сразу в недавно упавший провайдер. Запись идёт
    при каждой ошибке/восстановлении, чтение - при первом get_router().

Публичный API:
  call_llm_json(session, prompt, **kwargs)  -> Optional[dict]
  call_llm_text(session, prompt, **kwargs)  -> str

ai_groq.py продолжает существовать как тонкий shim поверх этого модуля,
чтобы не пришлось править ai_macro_sentinel/ai_regime/ai_postmortem.
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

# Ключ в memory.kv_store, под которым хранится состояние всех провайдеров.
_KV_KEY = "ai_router_breakers_v1"

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
    """Базовый класс провайдера. Каждый провайдер сам знает свой URL,
    свой формат запроса и как извлечь ответный текст."""

    name: str = ""
    enabled_attr: str = ""  # имя атрибута config с API-ключом

    # Состояние circuit-breaker.
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
        """CLOSED / OPEN / HALF_OPEN. Используется для логов и тестов."""
        if self._consecutive_errors < CIRCUIT_BREAKER_THRESHOLD:
            return "CLOSED"
        elapsed = time.time() - self._opened_at_epoch
        if elapsed >= CIRCUIT_BREAKER_RESET_SEC:
            return "HALF_OPEN"
        return "OPEN"

    def _record_success(self) -> None:
        if self._consecutive_errors > 0:
            print(f"[ROUTER] {self.name}: восстановлен, breaker -> CLOSED")
        self._consecutive_errors = 0
        self._opened_at_epoch = 0.0
        _persist_state()

    def _record_error(self) -> None:
        self._consecutive_errors += 1
        if self._consecutive_errors == CIRCUIT_BREAKER_THRESHOLD:
            self._opened_at_epoch = time.time()
            print(
                f"[ROUTER] {self.name}: {self._consecutive_errors} ошибок подряд, "
                f"breaker -> OPEN на {CIRCUIT_BREAKER_RESET_SEC}с"
            )
        _persist_state()

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
        """Вернуть raw text ответа модели или None при любой ошибке.
        Пометки в circuit-breaker делает сам внутри."""
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
                    body_text = await resp.text()
                    print(f"[ROUTER] groq HTTP 429: {body_text[:160]}")
                    # Rate limit - не ошибка провайдера, идём к следующему.
                    return None
                if resp.status != 200:
                    body_text = await resp.text()
                    print(f"[ROUTER] groq HTTP {resp.status}: {body_text[:200]}")
                    self._record_error()
                    return None
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            print(f"[ROUTER] groq сетевая ошибка: {exc}")
            self._record_error()
            return None
        except Exception as exc:  # noqa: BLE001
            print(f"[ROUTER] groq неожиданная ошибка: {exc}")
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
        except Exception as exc:  # noqa: BLE001
            print(f"[ROUTER] groq парс ответа: {exc}")
            self._record_error()
            return None

        self._record_success()
        return text


# --- Cerebras (OpenAI-совместимый, llama-3.3-70b) ------------------------

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
                    body_text = await resp.text()
                    print(f"[ROUTER] cerebras HTTP 429: {body_text[:160]}")
                    return None
                if resp.status != 200:
                    body_text = await resp.text()
                    print(f"[ROUTER] cerebras HTTP {resp.status}: {body_text[:200]}")
                    self._record_error()
                    return None
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            print(f"[ROUTER] cerebras сетевая ошибка: {exc}")
            self._record_error()
            return None
        except Exception as exc:  # noqa: BLE001
            print(f"[ROUTER] cerebras неожиданная ошибка: {exc}")
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
        except Exception as exc:  # noqa: BLE001
            print(f"[ROUTER] cerebras парс ответа: {exc}")
            self._record_error()
            return None

        self._record_success()
        return text


# --- Gemini (Google, generativelanguage.googleapis.com) ------------------

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
                    body_text = await resp.text()
                    print(f"[ROUTER] gemini HTTP 429: {body_text[:160]}")
                    return None
                if resp.status != 200:
                    body_text = await resp.text()
                    print(f"[ROUTER] gemini HTTP {resp.status}: {body_text[:200]}")
                    self._record_error()
                    return None
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            print(f"[ROUTER] gemini сетевая ошибка: {exc}")
            self._record_error()
            return None
        except Exception as exc:  # noqa: BLE001
            print(f"[ROUTER] gemini неожиданная ошибка: {exc}")
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
        except Exception as exc:  # noqa: BLE001
            print(f"[ROUTER] gemini парс ответа: {exc}")
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
        """Снимок состояния роутера для диагностики (например /status)."""
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
        any_attempted = False
        for provider in self.providers:
            if not provider.is_configured:
                continue
            if provider.state == "OPEN":
                # Пропускаем - breaker ещё не успел сбросить таймер.
                continue
            any_attempted = True
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
        if not any_attempted:
            print("[ROUTER] Все провайдеры либо не настроены, либо OPEN")
        return None


# Модульный синглтон. Создаётся ленивo, чтобы не падать при импорте.
_ROUTER: Optional[LLMRouter] = None


def _persist_state() -> None:
    """Сохранить snapshot всех breaker'ов в memory.kv_store.

    Хранится время выхода из OPEN (когда мы можем попробовать снова),
    а не «возраст» — иначе при долгом downtime после рестарта мы бы
    всё равно сразу провели probe, потеряв смысл сохранения. После
    рестарта load_state читает remaining time и восстанавливает счётчик
    ошибок только если ещё не пора probe-вызову.
    """
    if _ROUTER is None:
        return
    try:
        import memory  # ленивый импорт, чтобы избежать цикла

        snapshot = {}
        for p in _ROUTER.providers:
            snapshot[p.name] = {
                "errors": p._consecutive_errors,
                # абсолютное epoch-время, когда breaker сможет перейти в HALF_OPEN
                "open_until_epoch": (
                    p._opened_at_epoch + CIRCUIT_BREAKER_RESET_SEC
                    if p._opened_at_epoch > 0
                    else 0.0
                ),
            }
        memory.kv_set(_KV_KEY, snapshot)
    except Exception as exc:  # noqa: BLE001
        print(f"[ROUTER] persist: {exc}")


def _load_state(router: "LLMRouter") -> None:
    """Восстановить breaker'ы из memory.kv_store.

    Если open_until_epoch уже в прошлом — обнуляем счётчик, иначе
    выставляем _opened_at_epoch так, чтобы оставшееся время совпало
    с тем что было до рестарта.
    """
    try:
        import memory  # ленивый импорт

        snap = memory.kv_get(_KV_KEY, default={}) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"[ROUTER] load_state: {exc}")
        return
    now = time.time()
    for p in router.providers:
        info = snap.get(p.name)
        if not isinstance(info, dict):
            continue
        open_until = float(info.get("open_until_epoch") or 0.0)
        errors = int(info.get("errors") or 0)
        if open_until > now and errors >= CIRCUIT_BREAKER_THRESHOLD:
            # Breaker всё ещё OPEN. Восстанавливаем _opened_at_epoch так,
            # чтобы state property вернул "OPEN" пока не истечёт таймер.
            p._consecutive_errors = errors
            p._opened_at_epoch = open_until - CIRCUIT_BREAKER_RESET_SEC
            print(
                f"[ROUTER] {p.name}: восстановлен OPEN после рестарта, "
                f"осталось {open_until - now:.0f}с"
            )
        else:
            # Старое OPEN уже истекло либо счётчик не критичный — старт с CLOSED.
            p._consecutive_errors = 0
            p._opened_at_epoch = 0.0


def get_router() -> LLMRouter:
    global _ROUTER
    if _ROUTER is None:
        _ROUTER = LLMRouter()
        _load_state(_ROUTER)
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
        print(f"[ROUTER] Ответ LLM не распарсился как JSON: {text[:200]}")
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
