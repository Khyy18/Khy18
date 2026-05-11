"""ИИ-аналитик на основе Google Gemini.

Вызываем REST-эндпоинт generativelanguage.googleapis.com/v1beta/models/
gemini-2.0-flash:generateContent (публичной модели «Gemini 3 Flash» не
существует - используем актуальную быструю gemini-2.0-flash).

Ожидаемый ответ модели - СТРОГО JSON:
    {"decision": "APPROVE"|"REJECT", "confidence": 0-100, "reason": "..."}

Разрешаем модели оборачивать JSON в кодовые блоки ```json ... ```
- парсер устойчив к этому. При любой сетевой или парс-ошибке возвращаем
fail-closed вердикт REJECT/0, чтобы бот никогда не открывал сделку «вслепую».
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import aiohttp

import config


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_BARE_JSON_RE = re.compile(r"(\{[^{}]*\"decision\"[^{}]*\})", re.DOTALL)


def _build_prompt(
    technical_signal: dict[str, Any],
    news_headlines: list[str],
    recent_errors: list[dict[str, Any]],
) -> str:
    """Сформировать русскоязычный промпт для Gemini."""
    indicators = technical_signal.get("indicators", {}) or {}
    errors_lines: list[str] = []
    for e in recent_errors[:5]:
        errors_lines.append(
            "- "
            f"{e.get('ts', '?')} {e.get('symbol', '?')} {e.get('side', '?')} "
            f"entry={e.get('entry')} exit={e.get('exit')} pnl={e.get('pnl')} "
            f"reason={e.get('ai_reason')}"
        )
    errors_block = "\n".join(errors_lines) if errors_lines else "нет убытков в истории"

    news_block = (
        "\n".join(f"- {h}" for h in news_headlines[:10])
        if news_headlines
        else "нет свежих заголовков"
    )

    return (
        "Ты опытный крипто-аналитик. Оцени торговый сигнал и решай строго.\n"
        "Ответь ТОЛЬКО одним JSON-объектом без комментариев и пояснений.\n"
        "Формат ответа:\n"
        '{"decision": "APPROVE" или "REJECT", "confidence": число 0-100, '
        '"reason": "краткое обоснование на русском"}\n\n'
        f"Технический сигнал: {technical_signal.get('signal')}\n"
        f"Причина сигнала: {technical_signal.get('reason')}\n"
        f"Индикаторы: close={indicators.get('close')}, "
        f"EMA200={indicators.get('ema200')}, RSI={indicators.get('rsi')} "
        f"(пред. RSI={indicators.get('rsi_prev')}), ATR={indicators.get('atr')}\n"
        f"Планируемый вход={technical_signal.get('entry')}, "
        f"SL={technical_signal.get('sl')}, TP={technical_signal.get('tp')}\n\n"
        f"Свежие заголовки новостей:\n{news_block}\n\n"
        f"Последние убытки бота (учитывай их ошибки):\n{errors_block}\n\n"
        "Если сигнал сомнителен или противоречит новостному фону - возвращай REJECT.\n"
        "Если уверенность ниже 86 - возвращай REJECT."
    )


def _parse_model_json(text: str) -> Optional[dict[str, Any]]:
    """Извлечь JSON из ответа Gemini, устойчиво к ```json fences."""
    if not text:
        return None
    # 1) Пытаемся распарсить сразу.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 2) Ищем блок в fence.
    m = _FENCE_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 3) Ищем голый JSON с ключом decision.
    m = _BARE_JSON_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


def _normalize_verdict(raw: dict[str, Any]) -> dict[str, Any]:
    """Привести словарь к каноничному виду {decision, confidence, reason}."""
    decision = str(raw.get("decision", "")).strip().upper()
    if decision not in ("APPROVE", "REJECT"):
        decision = "REJECT"
    try:
        confidence = int(float(raw.get("confidence", 0)))
    except (TypeError, ValueError):
        confidence = 0
    confidence = max(0, min(100, confidence))
    reason = str(raw.get("reason", "")).strip() or "Без пояснения"
    return {"decision": decision, "confidence": confidence, "reason": reason}


def _fail_closed(detail: str) -> dict[str, Any]:
    return {
        "decision": "REJECT",
        "confidence": 0,
        "reason": f"Ошибка ИИ-анализа: {detail}",
    }


async def _call_gemini(
    session: aiohttp.ClientSession,
    prompt: str,
    timeout: int = 25,
) -> dict[str, Any]:
    """Низкоуровневый вызов Gemini. Возвращает нормализованный вердикт."""
    if not config.GEMINI_API_KEY:
        return _fail_closed("GEMINI_API_KEY не задан")

    url = f"{config.GEMINI_URL}?key={config.GEMINI_API_KEY}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.9,
            "maxOutputTokens": 256,
            "responseMimeType": "application/json",
        },
    }

    try:
        async with session.post(
            url,
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        ) as resp:
            if resp.status != 200:
                txt = await resp.text()
                return _fail_closed(f"Gemini статус {resp.status}: {txt[:200]}")
            data = await resp.json()
    except aiohttp.ClientError as exc:
        return _fail_closed(f"сеть Gemini: {exc}")
    except Exception as exc:  # noqa: BLE001
        return _fail_closed(f"неожиданная ошибка: {exc}")

    # Извлекаем текст из ответа.
    try:
        candidates = data.get("candidates") or []
        if not candidates:
            return _fail_closed("Gemini не вернул кандидатов")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
    except Exception as exc:  # noqa: BLE001
        return _fail_closed(f"разбор ответа: {exc}")

    parsed = _parse_model_json(text)
    if parsed is None:
        return _fail_closed(f"ответ не JSON: {text[:200]}")
    return _normalize_verdict(parsed)


async def decide(
    session: aiohttp.ClientSession,
    technical_signal: dict[str, Any],
    news_headlines: list[str],
    recent_errors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Основной гейт: спрашиваем ИИ, разрешать ли вход в сделку.

    Возвращает dict {decision, confidence, reason}.
    Внешний код должен открывать позицию только при decision == 'APPROVE'
    и confidence > 85.
    """
    if not technical_signal or not technical_signal.get("signal"):
        return _fail_closed("пустой технический сигнал")
    prompt = _build_prompt(technical_signal, news_headlines or [], recent_errors or [])
    return await _call_gemini(session, prompt)


async def explain_last_rejection(
    session: aiohttp.ClientSession,
    last_rejection: Optional[dict[str, Any]],
    recent_errors: list[dict[str, Any]],
) -> str:
    """Попросить Gemini человеко-читаемое объяснение последнего отклонения.
    Используется Telegram кнопкой «ПОЧЕМУ МИМО?»."""
    if not last_rejection:
        return "Отклонённых сигналов пока нет."

    ctx = last_rejection.get("context") or {}
    errors_lines = [
        f"- {e.get('ts')} {e.get('side')} pnl={e.get('pnl')} {e.get('ai_reason')}"
        for e in (recent_errors or [])[:5]
    ]
    errors_block = "\n".join(errors_lines) if errors_lines else "нет убытков в истории"

    prompt = (
        "Ты крипто-аналитик. Объясни простыми словами на русском языке, "
        "почему следующий сигнал был отклонён. 2-4 коротких предложения. "
        "Без JSON, без кодовых блоков, только текст.\n\n"
        f"Дата отклонения: {last_rejection.get('ts')}\n"
        f"Причина от модели: {last_rejection.get('reason')}\n"
        f"Уверенность: {last_rejection.get('confidence')}\n"
        f"Контекст сигнала: {json.dumps(ctx, ensure_ascii=False)[:800]}\n\n"
        f"Последние убытки бота:\n{errors_block}\n"
    )

    if not config.GEMINI_API_KEY:
        return "ИИ недоступен: GEMINI_API_KEY не задан."

    url = f"{config.GEMINI_URL}?key={config.GEMINI_API_KEY}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 256},
    }
    try:
        async with session.post(
            url,
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=25,
        ) as resp:
            if resp.status != 200:
                return f"ИИ вернул ошибку {resp.status}."
            data = await resp.json()
    except aiohttp.ClientError as exc:
        return f"Сетевая ошибка при обращении к ИИ: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Неожиданная ошибка ИИ: {exc}"

    try:
        parts = (
            (data.get("candidates") or [{}])[0].get("content") or {}
        ).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
    except Exception as exc:  # noqa: BLE001
        return f"Не удалось разобрать ответ ИИ: {exc}"

    return text or "ИИ не дал содержательного ответа."
