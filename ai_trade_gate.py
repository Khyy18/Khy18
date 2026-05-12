"""AI-veto gate перед открытием сделки (v3).

Архитектура
-----------
Gate - **последний страховочный слой** между детерминистическим решением
стратегии (strategy_v2 / strategy_v2_meanrevert) и фактическим ордером на
биржу. Стратегия и её фильтры (ATR, объём, режим, blackout) УЖЕ сказали
"открываем"; gate получает контекст сделки плюс свежие новости по символу
и задаёт Groq один узкий вопрос: есть ли в этих новостях хотя бы один
red-flag, из-за которого открывать позицию рискованно прямо сейчас?

Gate **не генерирует** свои сигналы - он только подтверждает или вето
существующий. Это важно: мы не делегируем торговое решение ИИ, а используем
его как дополнительный фильтр на катастрофические события, которые
детерминистические индикаторы поймать не могут (hack биржи, delisting,
SEC-расследование и подобное).

Режимы (config.AI_TRADE_GATE_MODE)
----------------------------------
- "off"    - gate выключен полностью, всегда возвращаем approve без вызова
             Groq. Сделка открывается если стратегия дала OK.
- "shadow" - gate вызывается, решение ЛОГИРУЕТСЯ, но не применяется. Сделка
             всегда открывается. Режим для наблюдения без риска повлиять на
             торговлю.
- "active" - решение применяется. veto блокирует вход.

Политика отказоустойчивости: **fail-CLOSED**
--------------------------------------------
На любой ошибке (сеть, таймаут, невалидный JSON от модели, пустой ответ)
возвращается {"verdict": "error", ...}. Верхний слой (main.py) в active
режиме трактует "error" так же как "veto" - сделка НЕ открывается. Логика:
если мы не можем убедиться, что новостной фон чист, безопаснее пропустить
сделку и дождаться следующего сигнала.

В shadow режиме "error" только логируется - на торговлю не влияет.

Публичная функция
-----------------
check_trade(session, *, symbol, side, strategy_name, entry_price, atr_pct,
            regime, regime_confidence, blackout, news_headlines)
    -> dict[str, Any]

Гарантированно возвращает dict формата
    {"verdict": "approve"|"veto"|"error", "reason": str, "confidence": int}
и НИКОГДА не raises. Все исключения ловятся внутри и конвертируются в
verdict="error".
"""

from __future__ import annotations

from typing import Any

import aiohttp

import ai_groq
import config


_ALLOWED_VERDICTS = ("approve", "veto")


def _error(reason: str) -> dict[str, Any]:
    """Сформировать ответ gate для ошибочных путей (fail-CLOSED сигнал)."""
    return {"verdict": "error", "reason": str(reason)[:200], "confidence": 0}


def _format_headlines_block(headlines: list[str], limit: int) -> str:
    """Пронумерованный список заголовков для подстановки в prompt."""
    if not headlines:
        return "(нет заголовков за выбранный интервал)"
    lines: list[str] = []
    for i, h in enumerate(headlines[:limit], start=1):
        h_clean = str(h or "").strip().replace("\n", " ")
        if h_clean:
            lines.append(f"{i}. {h_clean}")
    return "\n".join(lines) if lines else "(нет заголовков за выбранный интервал)"


def _build_prompt(
    *,
    symbol: str,
    side: str,
    strategy_name: str,
    entry_price: float,
    atr_pct: float,
    regime: str,
    regime_confidence: int,
    blackout: bool,
    news_headlines: list[str],
    news_limit: int,
) -> str:
    """Собрать prompt для Groq. Инструкция по умолчанию approve; veto
    разрешён только если один из перечисленных red-flag явно упомянут в
    заголовках И он касается нашего символа или биржи (OKX)."""
    hl_block = _format_headlines_block(news_headlines, news_limit)
    blackout_str = "ON" if blackout else "OFF"
    return (
        "Ты ай-veto gate для криптобота. Стратегия и все детерминистические "
        "фильтры уже решили открыть сделку. Твоя задача - найти в новостях "
        "СПИСОК red-flag рисков и, если хотя бы один явно применим к "
        "конкретной сделке, наложить veto. Не интерпретируй тренд, "
        "фундаментал, политику ФРС - это не твоя задача.\n\n"
        "Явные red-flags (только они дают veto):\n"
        "- hack биржи / exchange exploit;\n"
        "- депег стейблкоина;\n"
        "- rug pull проекта (команда украла ликвидность);\n"
        "- активное расследование SEC / CFTC / регулятора по символу;\n"
        "- major delisting с крупной биржи;\n"
        "- банкротство / неплатёжеспособность биржи;\n"
        "- критический баг смарт-контракта с потерей средств.\n\n"
        "ПО УМОЛЧАНИЮ verdict=approve. Verdict=veto ставь ТОЛЬКО если в "
        "списке новостей явно упомянут один из red-flags И он касается "
        "нашего символа или биржи OKX (на которой торгуем). Обычные "
        "новости про цену, прогнозы, общие рыночные комментарии, твиты "
        "инфлюенсеров - НЕ red-flag, это approve.\n\n"
        "Верни СТРОГО JSON без какого-либо текста вокруг:\n"
        "{\"verdict\": \"approve\"|\"veto\", "
        "\"reason\": \"короткая строка на русском, до 120 символов\", "
        "\"confidence\": 0-100}\n\n"
        "Параметры сделки:\n"
        f"- символ: {symbol}\n"
        f"- сторона: {side}\n"
        f"- стратегия: {strategy_name}\n"
        f"- цена входа: {entry_price}\n"
        f"- ATR(1h) / close: {atr_pct:.5f}\n"
        f"- режим рынка: {regime} (conf={regime_confidence})\n"
        f"- blackout macro-sentinel: {blackout_str}\n\n"
        f"Свежие заголовки по символу:\n{hl_block}\n"
    )


async def check_trade(
    session: aiohttp.ClientSession,
    *,
    symbol: str,
    side: str,
    strategy_name: str,
    entry_price: float,
    atr_pct: float,
    regime: str,
    regime_confidence: int,
    blackout: bool,
    news_headlines: list[str],
) -> dict[str, Any]:
    """Спросить Groq: approve/veto? Гарантированно возвращает dict, не raises.

    Формат ответа:
        {"verdict": "approve"|"veto"|"error",
         "reason": str,
         "confidence": int (0-100)}

    "error" означает сбой gate (сеть, таймаут, битый JSON). Верхний слой в
    active-режиме обязан трактовать "error" как veto (fail-CLOSED).
    """
    news_limit = int(getattr(config, "AI_TRADE_GATE_NEWS_LIMIT", 10) or 10)
    timeout = int(getattr(config, "AI_TRADE_GATE_TIMEOUT", 8) or 8)

    try:
        prompt = _build_prompt(
            symbol=str(symbol or "-"),
            side=str(side or "-").upper(),
            strategy_name=str(strategy_name or "-"),
            entry_price=float(entry_price or 0.0),
            atr_pct=float(atr_pct or 0.0),
            regime=str(regime or "TRENDING").upper(),
            regime_confidence=int(regime_confidence or 0),
            blackout=bool(blackout),
            news_headlines=list(news_headlines or []),
            news_limit=news_limit,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[AI-GATE] ошибка построения промпта: {exc}")
        return _error(f"ошибка построения промпта: {exc}")

    try:
        parsed = await ai_groq.call_groq_json(
            session,
            prompt,
            max_output_tokens=128,
            temperature=0.1,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[AI-GATE] ошибка вызова Groq: {exc}")
        return _error(f"ошибка вызова groq: {exc}")

    if not isinstance(parsed, dict):
        # call_groq_json сам уже залогировал причину (сеть, таймаут, битый JSON).
        return _error("groq недоступен")

    verdict_raw = str(parsed.get("verdict", "") or "").strip().lower()
    if verdict_raw not in _ALLOWED_VERDICTS:
        # Ответ формально есть, но verdict не из белого списка - fail-CLOSED.
        return _error(f"неожиданный verdict={verdict_raw!r}")

    reason = str(parsed.get("reason", "") or "").strip()[:200]

    try:
        conf_num = int(float(parsed.get("confidence", 50)))
    except (TypeError, ValueError):
        conf_num = 50
    confidence = max(0, min(100, conf_num))

    return {"verdict": verdict_raw, "reason": reason, "confidence": confidence}
