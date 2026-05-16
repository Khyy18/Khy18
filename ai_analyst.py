"""Остаточный модуль ai_analyst.

В v1 здесь жил Gemini-гейт, решавший APPROVE/REJECT на входе в сделку.
В v2 гейтинг перенесён в strategy_v2 + ai_macro_sentinel + ai_regime,
а ai_analyst.decide() удалён как публичный контракт.

Для обратной совместимости сохранены два имени:
  - decide(*args, **kwargs): stub, бросает NotImplementedError. Нужен
    только чтобы main.py (старый торговый цикл) продолжал импортироваться
    до тех пор, пока FEAT-004 не перепишет loop под strategy_v2.
  - explain_last_rejection(session, last_rejection, recent_errors) -> str:
    переориентирована на детерминированные фильтры (Donchian-пробой,
    blackout, режим CRISIS и т.п.). На вход принимает словарь
    {ts, symbol, filter, detail, indicators}. Старая форма (с reason/
    confidence от модели) также принимается - мы просто читаем что есть
    через .get(...).  Функция НИКОГДА не бросает исключений: на любой
    сбой возвращается короткий русский fallback-текст.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import aiohttp

import ai_groq
import config


async def decide(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Старый ИИ-гейт v1. В v2 снят - входы решают strategy_v2 + ai_macro_sentinel.

    Поднимает NotImplementedError намеренно: если кто-то всё ещё зовёт этот
    коллбек в рантайме, нужно перевести его на v2-путь, а не тихо вернуть
    fail-closed вердикт.
    """
    raise NotImplementedError(
        "decide() снят в v2, используйте strategy_v2 + ai_macro_sentinel/ai_regime"
    )


def _format_fallback(last_rejection: dict[str, Any]) -> str:
    """Детерминированный человеко-читаемый текст без обращения к Gemini."""
    ts = last_rejection.get("ts") or "-"
    symbol = last_rejection.get("symbol") or "-"
    flt = last_rejection.get("filter") or last_rejection.get("reason") or "не указан"
    detail = last_rejection.get("detail") or ""
    indicators = last_rejection.get("indicators") or {}
    ind_line = ""
    if isinstance(indicators, dict) and indicators:
        try:
            ind_line = ", ".join(
                f"{k}={v}" for k, v in list(indicators.items())[:6]
            )
        except Exception:  # noqa: BLE001
            ind_line = ""
    parts = [
        f"Последнее отклонение: {ts} по {symbol}.",
        f"Сработавший фильтр: {flt}.",
    ]
    if detail:
        parts.append(str(detail))
    if ind_line:
        parts.append(f"Индикаторы: {ind_line}.")
    return " ".join(parts)


async def explain_last_rejection(
    session: aiohttp.ClientSession,
    last_rejection: Optional[dict[str, Any]],
    recent_errors: Optional[list[dict[str, Any]]] = None,
) -> str:
    """Объяснение последнего отклонённого сигнала для кнопки «ПОЧЕМУ МИМО?».

    Пробует получить более живую формулировку у Gemini, при любой проблеме
    отдаёт детерминированный русский fallback. Никогда не бросает.
    """
    if not last_rejection:
        return "Отклонённых сигналов пока нет."

    fallback = _format_fallback(last_rejection)

    # Если ключ Groq не задан, модель не зовём - fallback честнее.
    if not getattr(config, "GROQ_API_KEY", ""):
        return fallback

    try:
        recent_block = ""
        if recent_errors:
            lines = []
            for e in list(recent_errors)[:5]:
                if not isinstance(e, dict):
                    continue
                lines.append(
                    "- "
                    f"{e.get('ts', '?')} {e.get('symbol', '?')} "
                    f"{e.get('side', '?')} pnl={e.get('pnl')} "
                    f"{e.get('ai_reason') or e.get('filter') or ''}"
                )
            recent_block = "\n".join(lines)
        if not recent_block:
            recent_block = "нет недавних ошибок"

        indicators = last_rejection.get("indicators") or {}
        try:
            ind_json = json.dumps(indicators, ensure_ascii=False)[:600]
        except (TypeError, ValueError):
            ind_json = str(indicators)[:600]

        prompt = (
            "Ты крипто-аналитик. Объясни простыми словами на русском языке, "
            "почему последний торговый сигнал был отклонён детерминированным "
            "фильтром. 2-4 коротких предложения. Без JSON, без кодовых "
            "блоков, только связный текст.\n\n"
            f"Время: {last_rejection.get('ts') or '-'}\n"
            f"Символ: {last_rejection.get('symbol') or '-'}\n"
            "Сработавший фильтр: "
            f"{last_rejection.get('filter') or last_rejection.get('reason') or '-'}\n"
            f"Детали: {last_rejection.get('detail') or '-'}\n"
            f"Индикаторы: {ind_json}\n\n"
            f"Недавние убытки бота:\n{recent_block}\n"
        )
        text = await ai_groq.call_groq_text(
            session,
            prompt,
            max_output_tokens=256,
            temperature=0.3,
            timeout=25,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[AI] explain_last_rejection: сбой вызова Groq: {exc}")
        return fallback

    text = (text or "").strip()
    return text if text else fallback
