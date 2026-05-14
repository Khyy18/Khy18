"""Единый реестр квот LLM-провайдеров для Multi-Strategy Ensemble.

Каждый ИИ-клиент (ai_groq, будущие ai_cerebras / ai_openrouter / ai_gemini)
обновляет свой снапшот через update_*-функцию на каждом HTTP-ответе.
Telegram-бот читает get_*_snapshot() для отображения в карточке "🛰 ИИ-слои".

Принципы:
  - Никаких сетевых вызовов на уровне модуля.
  - Никакого глобального state кроме словаря-снапшота.
  - На любую ошибку парса заголовков — оставляем старые значения, пишем лог.
  - updated_epoch == 0.0 → снапшот ещё не заполнялся (первый вызов
    провайдера ещё не состоялся). Бот показывает "Снапшот ещё не получен".

Поддерживаемые провайдеры:
  - groq:       headers x-ratelimit-* (RPD/TPD/RPM)
  - cerebras:   headers x-ratelimit-* (OpenAI-совместимый, тот же формат)
  - openrouter: headers x-ratelimit-* + отдельный GET /api/v1/key
  - gemini:     headers НЕТ → локальный счётчик RPD c фиксированным потолком
"""

from __future__ import annotations

import time
from typing import Any, Optional


# ──────────────────────────────────────────────────────────────────────
# Снапшоты квот. Структура одинаковая для всех — чтобы бот рендерил единым
# шаблоном. Поля, которых у провайдера нет, остаются 0/"".
#
# Поля:
#   updated_epoch  : time.time() последнего обновления (0.0 = не заполнялся)
#   provider       : имя провайдера для UI (Groq / Cerebras / Gemini / OR)
#   rpd_limit/used : запросы в сутки (used = limit - remaining)
#   tpd_limit/used : токены в сутки
#   rpm_limit/used : запросы в минуту
#   rpd_reset      : строка "1h 12m" или "—" - когда сбросится суточный лимит
#   rpm_reset      : то же для минутного
#   note           : произвольная пометка (например "локальный счётчик")
# ──────────────────────────────────────────────────────────────────────

def _empty_snapshot(provider: str) -> dict[str, Any]:
    return {
        "updated_epoch": 0.0,
        "provider": provider,
        "rpd_limit": 0, "rpd_used": 0,
        "tpd_limit": 0, "tpd_used": 0,
        "rpm_limit": 0, "rpm_used": 0,
        "rpd_reset": "",
        "rpm_reset": "",
        "note": "",
    }


_groq_snap = _empty_snapshot("Groq")
_cerebras_snap = _empty_snapshot("Cerebras")
_openrouter_snap = _empty_snapshot("OpenRouter")
_gemini_snap = _empty_snapshot("Gemini")


def _parse_int_safe(value: Any) -> int:
    """Парс int из HTTP-заголовка. На ошибке возвращает 0."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


# ──────────────────────────────────────────────────────────────────────
# Groq
# ──────────────────────────────────────────────────────────────────────

def update_groq_from_headers(headers: Any) -> None:
    """Обновить снапшот Groq из x-ratelimit-* заголовков ответа.

    Groq возвращает OpenAI-совместимые заголовки на КАЖДОМ ответе (200/429/любой).
    Все заголовки опциональны — отсутствующие интерпретируем как 0/"".
    """
    try:
        rpd_limit = _parse_int_safe(headers.get("x-ratelimit-limit-requests", 0))
        rpd_remaining = _parse_int_safe(headers.get("x-ratelimit-remaining-requests", 0))
        tpd_limit = _parse_int_safe(headers.get("x-ratelimit-limit-tokens", 0))
        tpd_remaining = _parse_int_safe(headers.get("x-ratelimit-remaining-tokens", 0))
        rpm_limit = _parse_int_safe(
            headers.get("x-ratelimit-limit-requests-per-minute", 0)
        )
        rpm_remaining = _parse_int_safe(
            headers.get("x-ratelimit-remaining-requests-per-minute", 0)
        )
        _groq_snap.update({
            "updated_epoch": time.time(),
            "rpd_limit": rpd_limit,
            "rpd_used": max(0, rpd_limit - rpd_remaining),
            "tpd_limit": tpd_limit,
            "tpd_used": max(0, tpd_limit - tpd_remaining),
            "rpm_limit": rpm_limit,
            "rpm_used": max(0, rpm_limit - rpm_remaining),
            "rpd_reset": str(headers.get("x-ratelimit-reset-requests", "")),
            "rpm_reset": str(
                headers.get("x-ratelimit-reset-requests-per-minute", "")
            ),
        })
    except Exception as exc:  # noqa: BLE001
        print(f"[QUOTAS] Groq: не удалось распарсить заголовки: {exc}")


def get_groq_snapshot() -> dict[str, Any]:
    return dict(_groq_snap)


# ──────────────────────────────────────────────────────────────────────
# Cerebras (OpenAI-совместимые заголовки, формат идентичен Groq)
# ──────────────────────────────────────────────────────────────────────

def update_cerebras_from_headers(headers: Any) -> None:
    """Cerebras Inference API возвращает те же x-ratelimit-* что и OpenAI/Groq."""
    try:
        rpd_limit = _parse_int_safe(headers.get("x-ratelimit-limit-requests", 0))
        rpd_remaining = _parse_int_safe(headers.get("x-ratelimit-remaining-requests", 0))
        tpd_limit = _parse_int_safe(headers.get("x-ratelimit-limit-tokens", 0))
        tpd_remaining = _parse_int_safe(headers.get("x-ratelimit-remaining-tokens", 0))
        rpm_limit = _parse_int_safe(
            headers.get("x-ratelimit-limit-requests-per-minute", 0)
        )
        rpm_remaining = _parse_int_safe(
            headers.get("x-ratelimit-remaining-requests-per-minute", 0)
        )
        _cerebras_snap.update({
            "updated_epoch": time.time(),
            "rpd_limit": rpd_limit,
            "rpd_used": max(0, rpd_limit - rpd_remaining),
            "tpd_limit": tpd_limit,
            "tpd_used": max(0, tpd_limit - tpd_remaining),
            "rpm_limit": rpm_limit,
            "rpm_used": max(0, rpm_limit - rpm_remaining),
            "rpd_reset": str(headers.get("x-ratelimit-reset-requests", "")),
            "rpm_reset": str(
                headers.get("x-ratelimit-reset-requests-per-minute", "")
            ),
        })
    except Exception as exc:  # noqa: BLE001
        print(f"[QUOTAS] Cerebras: не удалось распарсить заголовки: {exc}")


def get_cerebras_snapshot() -> dict[str, Any]:
    return dict(_cerebras_snap)


# ──────────────────────────────────────────────────────────────────────
# OpenRouter
# ──────────────────────────────────────────────────────────────────────

def update_openrouter_from_headers(headers: Any) -> None:
    """OpenRouter возвращает x-ratelimit-* в заголовках обычных запросов.

    Поля точные:
      x-ratelimit-limit         — суточный лимит (50 на free, 1000 на paid)
      x-ratelimit-remaining     — осталось
      x-ratelimit-reset         — unix epoch ms сброса
    Минутного лимита OpenRouter в этих заголовках не отдаёт, но он известен
    (20/min на free) — заполняем фиксированным значением для отображения
    шкалы, used оставляем 0 (точного счёта на минуту нет).
    """
    try:
        rpd_limit = _parse_int_safe(headers.get("x-ratelimit-limit", 0))
        rpd_remaining = _parse_int_safe(headers.get("x-ratelimit-remaining", 0))
        reset_ms = _parse_int_safe(headers.get("x-ratelimit-reset", 0))
        # Сброс в человеко-читаемой форме (delta от now).
        rpd_reset = ""
        if reset_ms > 0:
            delta_sec = max(0, int(reset_ms / 1000.0 - time.time()))
            if delta_sec >= 3600:
                rpd_reset = f"{delta_sec // 3600}h {(delta_sec % 3600) // 60}m"
            else:
                rpd_reset = f"{delta_sec // 60}m {delta_sec % 60}s"
        _openrouter_snap.update({
            "updated_epoch": time.time(),
            "rpd_limit": rpd_limit,
            "rpd_used": max(0, rpd_limit - rpd_remaining),
            "rpm_limit": 20,  # free-tier потолок — не отдаётся в headers
            "rpm_used": 0,
            "rpd_reset": rpd_reset,
            "note": "free 50/day, paid 1000/day",
        })
    except Exception as exc:  # noqa: BLE001
        print(f"[QUOTAS] OpenRouter: не удалось распарсить заголовки: {exc}")


def get_openrouter_snapshot() -> dict[str, Any]:
    return dict(_openrouter_snap)


# ──────────────────────────────────────────────────────────────────────
# Gemini (Google AI Studio) — заголовков с лимитами НЕТ.
# Используем локальный счётчик: каждый успешный вызов клиент инкрементит.
# Сброс — в полночь UTC (24h rolling). Реализован простой rolling-счётчик
# через эпоху начала суток.
# ──────────────────────────────────────────────────────────────────────

# Известные потолки free-tier Gemini-2.5-Flash на момент Май 2026.
# Источник: https://ai.google.dev/gemini-api/docs/rate-limits
_GEMINI_RPD_LIMIT = 1500   # requests per day
_GEMINI_RPM_LIMIT = 15     # requests per minute

# Счётчики (хранятся в памяти процесса; сбрасываются при рестарте бота).
_gemini_day_start_epoch: float = 0.0
_gemini_minute_start_epoch: float = 0.0
_gemini_rpd_used: int = 0
_gemini_rpm_used: int = 0


def _seconds_to_human(sec: int) -> str:
    sec = max(0, int(sec))
    if sec >= 3600:
        return f"{sec // 3600}h {(sec % 3600) // 60}m"
    if sec >= 60:
        return f"{sec // 60}m {sec % 60}s"
    return f"{sec}s"


def increment_gemini_call() -> None:
    """Учесть успешный вызов Gemini.

    Клиент вызывает после каждого 200-OK (для 429 — НЕ инкрементить, т.к.
    запрос не выполнен).
    """
    global _gemini_day_start_epoch, _gemini_minute_start_epoch
    global _gemini_rpd_used, _gemini_rpm_used

    now = time.time()

    # Rolling 24h.
    if now - _gemini_day_start_epoch >= 86400:
        _gemini_day_start_epoch = now
        _gemini_rpd_used = 0
    # Rolling 60s.
    if now - _gemini_minute_start_epoch >= 60:
        _gemini_minute_start_epoch = now
        _gemini_rpm_used = 0

    _gemini_rpd_used += 1
    _gemini_rpm_used += 1

    rpd_reset_in = max(0, int(86400 - (now - _gemini_day_start_epoch)))
    rpm_reset_in = max(0, int(60 - (now - _gemini_minute_start_epoch)))

    _gemini_snap.update({
        "updated_epoch": now,
        "rpd_limit": _GEMINI_RPD_LIMIT,
        "rpd_used": _gemini_rpd_used,
        "rpm_limit": _GEMINI_RPM_LIMIT,
        "rpm_used": _gemini_rpm_used,
        "rpd_reset": _seconds_to_human(rpd_reset_in),
        "rpm_reset": _seconds_to_human(rpm_reset_in),
        "note": "локальный счётчик (Google headers с лимитами не отдаёт)",
    })


def get_gemini_snapshot() -> dict[str, Any]:
    """Снапшот Gemini. Если ни одного вызова не было — updated_epoch=0.0,
    но лимиты возвращаем известные (бот может показать пустые бары)."""
    snap = dict(_gemini_snap)
    if snap["updated_epoch"] == 0.0:
        # Известные потолки даже до первого вызова — для рендера шкалы.
        snap["rpd_limit"] = _GEMINI_RPD_LIMIT
        snap["rpm_limit"] = _GEMINI_RPM_LIMIT
        snap["note"] = "локальный счётчик (вызовов ещё не было)"
    return snap


# ──────────────────────────────────────────────────────────────────────
# Универсальный getter для UI: список всех снапшотов в стабильном порядке.
# ──────────────────────────────────────────────────────────────────────

def get_all_snapshots() -> list[dict[str, Any]]:
    """Список снапшотов в порядке отображения в карточке "🛰 ИИ-слои".

    Бот итерирует по этому списку и рисует один блок на провайдера через
    общий шаблон (имя, прогресс-бары RPD/TPD/RPM, тайминги сброса, note).
    """
    return [
        get_groq_snapshot(),
        get_cerebras_snapshot(),
        get_openrouter_snapshot(),
        get_gemini_snapshot(),
    ]
