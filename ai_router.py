"""LLMRouter с failover между провайдерами.

Зачем нужен:
  Прежде вся ИИ-инфраструктура (ai_trade_gate, ai_macro_sentinel, ai_regime,
  ai_postmortem, ai_analyst) ходила в Groq напрямую. При деградации Groq
  бот терял всё ИИ сразу: AI-Gate в active-режиме блокировал ВСЕ сделки
  (fail-CLOSED), Regime classifier застревал, Macro-sentinel переставал
  обновлять blackout, Postmortem не выходил.

Идея router'а:
  Один общий слой failover. Провайдеры пробуются по приоритету; при ошибке
  любого свойства (network, 429, 5xx, парс JSON) — переходим к следующему.
  Все провайдеры OpenAI-совместимы по формату /chat/completions, так что
  единый prompt подходит всем.

Приоритет (Май 2026):
  1. Groq        — primary, llama-3.3-70b-versatile, ~14400 RPD / 30 RPM,
                   быстрее всех (0.3-0.8с), JSON-mode стабилен.
  2. Cerebras    — backup, gpt-oss-120b, OpenAI-совместимый, ~24M токенов/сутки.
                   API-схема идентична Groq (drop-in заменa).
  3. Gemini      — last-resort, gemini-2.5-flash, 1500 RPD / 15 RPM. Формат
                   запроса другой (Google API), формат ответа тоже другой —
                   обработка через отдельный адаптер.

Все вызовы возвращают dict (parsed JSON) или None при сбое всех провайдеров.
Никаких raise — верхний слой получает None и применяет свою fail-* политику.

Публичные функции:
  call_json(session, prompt, **kwargs) -> Optional[dict]
  call_text(session, prompt, **kwargs) -> str
  get_last_provider() -> str   # для логов/диагностики

Конфигурация:
  config.GROQ_API_KEY        — primary
  config.CEREBRAS_API_KEY    — backup (опционально)
  config.GOOGLE_AI_KEY       — last-resort (опционально)
  config.LLM_ROUTER_DISABLED — если "1"/"true", router отключён, ходим
                                только в Groq (как раньше).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Optional

import aiohttp

import config


# --- Состояние и backoff между провайдерами --------------------------------

# Имя последнего успешно ответившего провайдера (для UI / логов).
_last_provider: str = ""

# Простой circuit-breaker per-provider: если провайдер ответил ошибкой,
# на _CB_COOLDOWN_SEC мы его пропускаем и сразу идём к следующему.
# Это предотвращает лишние таймауты на каждом тике, когда провайдер лежит.
_CB_COOLDOWN_SEC = 120
_provider_blocked_until: dict[str, float] = {}


def _is_blocked(name: str) -> bool:
    until = _provider_blocked_until.get(name, 0.0)
    return time.time() < until


def _block_provider(name: str, exc_info: str = "") -> None:
    _provider_blocked_until[name] = time.time() + _CB_COOLDOWN_SEC
    print(f"[ROUTER] {name} заблокирован на {_CB_COOLDOWN_SEC}с: {exc_info[:120]}")


def get_last_provider() -> str:
    """Имя провайдера, обслужившего последний успешный вызов. Пусто, если
    ни один не отвечал или router ещё не вызывался."""
    return _last_provider


def get_provider_status() -> dict[str, dict[str, Any]]:
    """Снапшот состояния circuit-breaker'ов всех провайдеров.

    Используется Telegram-ботом для UI-карточки «🛰 ИИ-слои» (показ
    активного / заблокированного состояния по каждому провайдеру).
    """
    now = time.time()
    out: dict[str, dict[str, Any]] = {}
    for name in ("groq", "cerebras", "gemini"):
        until = _provider_blocked_until.get(name, 0.0)
        blocked = until > now
        out[name] = {
            "blocked": blocked,
            "blocked_for_sec": max(0, int(until - now)) if blocked else 0,
        }
    return out


# --- JSON-парсер (общий, как в ai_groq) ------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_BARE_JSON_RE = re.compile(r"(\{[\s\S]*\})")


def _parse_model_json(text: str) -> Optional[dict[str, Any]]:
    """Извлечь JSON из произвольного ответа модели (с устойчивостью к fence)."""
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


# --- Провайдер: Groq -------------------------------------------------------

async def _call_groq(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    response_format_json: bool,
    max_output_tokens: int,
    temperature: float,
    timeout: int,
) -> Optional[str]:
    """Вернуть содержимое choices[0].message.content или None при ошибке."""
    if not getattr(config, "GROQ_API_KEY", "") or _is_blocked("groq"):
        return None

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
            getattr(config, "GROQ_URL", "https://api.groq.com/openai/v1/chat/completions"),
            data=json.dumps(body, ensure_ascii=False),
            headers=headers,
            timeout=timeout,
        ) as resp:
            # Зеркалим квоту в общий реестр (как делает ai_groq.py).
            try:
                import ai_quotas
                ai_quotas.update_groq_from_headers(resp.headers)
            except Exception:  # noqa: BLE001
                pass
            if resp.status == 429:
                _block_provider("groq", "HTTP 429")
                return None
            if resp.status >= 500:
                _block_provider("groq", f"HTTP {resp.status}")
                return None
            if resp.status != 200:
                body_text = await resp.text()
                print(f"[ROUTER] Groq HTTP {resp.status}: {body_text[:160]}")
                return None
            data = await resp.json()
            choices = data.get("choices") or []
            if not choices:
                return None
            return str(choices[0].get("message", {}).get("content", "") or "").strip()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        _block_provider("groq", str(exc))
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[ROUTER] Groq неожиданная ошибка: {exc}")
        return None


# --- Провайдер: Cerebras (OpenAI-совместимый, drop-in для Groq) -----------

async def _call_cerebras(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    response_format_json: bool,
    max_output_tokens: int,
    temperature: float,
    timeout: int,
) -> Optional[str]:
    api_key = getattr(config, "CEREBRAS_API_KEY", "")
    if not api_key or _is_blocked("cerebras"):
        return None

    body: dict[str, Any] = {
        "model": getattr(config, "CEREBRAS_MODEL", "gpt-oss-120b"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": float(temperature),
        "max_tokens": int(max_output_tokens),
    }
    if response_format_json:
        body["response_format"] = {"type": "json_object"}

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    url = getattr(
        config, "CEREBRAS_URL", "https://api.cerebras.ai/v1/chat/completions"
    )
    try:
        async with session.post(
            url,
            data=json.dumps(body, ensure_ascii=False),
            headers=headers,
            timeout=timeout,
        ) as resp:
            try:
                import ai_quotas
                ai_quotas.update_cerebras_from_headers(resp.headers)
            except Exception:  # noqa: BLE001
                pass
            if resp.status == 429:
                _block_provider("cerebras", "HTTP 429")
                return None
            if resp.status >= 500:
                _block_provider("cerebras", f"HTTP {resp.status}")
                return None
            if resp.status != 200:
                body_text = await resp.text()
                print(f"[ROUTER] Cerebras HTTP {resp.status}: {body_text[:160]}")
                return None
            data = await resp.json()
            choices = data.get("choices") or []
            if not choices:
                return None
            return str(choices[0].get("message", {}).get("content", "") or "").strip()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        _block_provider("cerebras", str(exc))
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[ROUTER] Cerebras неожиданная ошибка: {exc}")
        return None


# --- Провайдер: Gemini (Google API, формат свой) --------------------------

async def _call_gemini(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    response_format_json: bool,
    max_output_tokens: int,
    temperature: float,
    timeout: int,
) -> Optional[str]:
    api_key = getattr(config, "GOOGLE_AI_KEY", "")
    if not api_key or _is_blocked("gemini"):
        return None

    model = getattr(config, "GEMINI_MODEL", "gemini-2.5-flash")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": float(temperature),
            "maxOutputTokens": int(max_output_tokens),
        },
    }
    if response_format_json:
        body["generationConfig"]["responseMimeType"] = "application/json"

    headers = {"Content-Type": "application/json"}
    try:
        async with session.post(
            url,
            data=json.dumps(body, ensure_ascii=False),
            headers=headers,
            timeout=timeout,
        ) as resp:
            if resp.status == 429:
                _block_provider("gemini", "HTTP 429")
                return None
            if resp.status >= 500:
                _block_provider("gemini", f"HTTP {resp.status}")
                return None
            if resp.status != 200:
                body_text = await resp.text()
                print(f"[ROUTER] Gemini HTTP {resp.status}: {body_text[:160]}")
                return None
            data = await resp.json()
            try:
                import ai_quotas
                ai_quotas.increment_gemini_call()
            except Exception:  # noqa: BLE001
                pass
            candidates = data.get("candidates") or []
            if not candidates:
                return None
            content = candidates[0].get("content") or {}
            parts = content.get("parts") or []
            if not parts:
                return None
            return str(parts[0].get("text", "") or "").strip()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        _block_provider("gemini", str(exc))
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[ROUTER] Gemini неожиданная ошибка: {exc}")
        return None


# --- Универсальный диспатчер ----------------------------------------------

# Порядок попыток. Тhe first non-empty response wins.
_PROVIDER_ORDER: tuple[tuple[str, Any], ...] = (
    ("groq", _call_groq),
    ("cerebras", _call_cerebras),
    ("gemini", _call_gemini),
)


def _router_disabled() -> bool:
    """Если выставлен флаг отключения — router ходит только в Groq.

    Используется как exit-стратегия, если в проде Cerebras/Gemini ведут себя
    непредсказуемо. Включается переменной окружения LLM_ROUTER_DISABLED=1.
    """
    val = str(getattr(config, "LLM_ROUTER_DISABLED", "") or "").strip().lower()
    return val in ("1", "true", "yes", "on")


async def call_json(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    max_output_tokens: int = 256,
    temperature: float = 0.2,
    timeout: int = 25,
) -> Optional[dict[str, Any]]:
    """Спросить LLM о JSON-ответе с failover между провайдерами.

    Возвращает dict (parsed JSON) или None если ВСЕ провайдеры упали.
    Имя последнего ответившего провайдера сохраняется в get_last_provider().
    """
    global _last_provider
    providers = (
        (_PROVIDER_ORDER[0],) if _router_disabled() else _PROVIDER_ORDER
    )
    for name, fn in providers:
        text = await fn(
            session,
            prompt,
            response_format_json=True,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            timeout=timeout,
        )
        if not text:
            continue
        parsed = _parse_model_json(text)
        if parsed is None:
            print(f"[ROUTER] {name}: ответ не распарсился как JSON: {text[:160]}")
            continue
        _last_provider = name
        if name != "groq":
            print(f"[ROUTER] failover: ответ от {name}")
        return parsed
    _last_provider = ""
    return None


async def call_text(
    session: aiohttp.ClientSession,
    prompt: str,
    *,
    max_output_tokens: int = 512,
    temperature: float = 0.3,
    timeout: int = 25,
) -> str:
    """Спросить LLM о свободном тексте с failover. На полный сбой — пустая строка."""
    global _last_provider
    providers = (
        (_PROVIDER_ORDER[0],) if _router_disabled() else _PROVIDER_ORDER
    )
    for name, fn in providers:
        text = await fn(
            session,
            prompt,
            response_format_json=False,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            timeout=timeout,
        )
        if text:
            _last_provider = name
            if name != "groq":
                print(f"[ROUTER] failover: ответ от {name}")
            return text
    _last_provider = ""
    return ""
